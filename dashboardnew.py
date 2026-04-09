import streamlit as st
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import requests
import asyncio
import aiohttp
from concurrent.futures import ThreadPoolExecutor
from data_queries import init_connection, list_all_tenant_devices, get_device_data

st.set_page_config(
    page_title="Dashboard Permacultura Tech",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📊 Dashboard Permacultura Tech")

TB_URL = "https://tb.permaculturatech.com"  # centralizado aquí

# ===== CONSTANTES (fuera del flujo de render) =====
KEY_MAPPING = {
    "temperature": "Temperatura del suelo",
    "humidity": "Contenido Volumétrico",
    "soil_conductivity": "Conductividad aparente"
}

PARAMETROS = {
    "humidity": {
        "label": "Humedad Volumétrica del Suelo (VWC %)",
        "unit": "%",
        "verde": (25, 40),
        "amarillo": [(18, 24), (41, 45)],
        "rojo": [(0, 18), (45, 100)]
    },
    "temperature": {
        "label": "Temperatura del Suelo",
        "unit": "°C",
        "verde": (18, 28),
        "amarillo": [(12, 17), (29, 32)],
        "rojo": [(0, 12), (32, 100)]
    },
    "soil_conductivity": {
        "label": "Conductividad Eléctrica (CE aparente)",
        "unit": "dS/m",
        "verde": (0.2, 1.2),
        "amarillo": [(1.3, 2.0)],
        "rojo": [(2.0, 4.0), (4.0, 100)]
    }
}

ORDEN_PERIODOS = ["Mañana", "Tarde", "Noche"]

# ===== CONEXIÓN: JWT en session_state, no como argumento cacheado =====
if "jwt_token" not in st.session_state:
    try:
        jwt_token, refresh_token = init_connection()
        st.session_state["jwt_token"] = jwt_token
    except Exception as e:
        st.error(f"Error de conexión a ThingsBoard: {e}")
        st.stop()

jwt_token = st.session_state["jwt_token"]

# ===== FUNCIONES PURAS (sin jwt_token como argumento cacheado) =====
def clasificar_periodo(hora):
    if 6 <= hora < 12:
        return "Mañana"
    elif 12 <= hora < 18:
        return "Tarde"
    return "Noche"

def determinar_estado(valor, key):
    config = PARAMETROS.get(key, {})
    verde_min, verde_max = config.get("verde", (0, 0))
    if verde_min <= valor <= verde_max:
        return "Óptimo", "#2ecc71"
    for mn, mx in config.get("amarillo", []):
        if mn <= valor <= mx:
            return "Precaución", "#f39c12"
    for mn, mx in config.get("rojo", []):
        if mn <= valor <= mx:
            return "Crítico", "#e74c3c"
    return "Desconocido", "#95a5a6"

def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))

def riesgo_bloqueo(hum, temp, ec, w_h=0.35, w_t=0.15, w_e=0.50, t_low=15, t_high=25):
    H_risk = clamp((100.0 - hum) / 100.0)
    if t_low <= temp <= t_high:
        T_risk = 0.0
    elif temp > t_high:
        T_risk = clamp((temp - t_high) / 15.0)
    else:
        T_risk = clamp((t_low - temp) / 15.0)
    EC_risk = clamp((ec - 1.0) / (4.0 - 1.0))
    R_raw = w_h * H_risk + w_t * T_risk + w_e * EC_risk
    return {"H_risk": H_risk, "T_risk": T_risk, "EC_risk": EC_risk, "R_raw": R_raw, "R_0_10": round(R_raw * 10.0, 1)}

def clasificar_ce(ce):
    if ce < 1.0: return "Bajo"
    elif ce < 2.5: return "Medio"
    elif ce < 4.0: return "Alto"
    return "Muy alto"

def recomendacion_ce(cat):
    return {
        "Bajo": "Suelo sano. Mantén riegos normales.",
        "Medio": "Acumulación leve. Aumenta ligeramente el riego y revisa fertilización.",
        "Alto": "Riesgo de estrés. Aplica riegos largos y evita fertilizantes salinos.",
        "Muy alto": "Salinidad peligrosa. Realiza lavado de sales y revisa calidad del agua."
    }[cat]

def color_ce(cat):
    return {"Bajo": "#2ecc71", "Medio": "#f39c12", "Alto": "#e67e22", "Muy alto": "#e74c3c"}[cat]

# ===== CARGA DE DISPOSITIVOS =====
@st.cache_data(ttl=3600)
def cargar_dispositivos():
    return list_all_tenant_devices(st.session_state["jwt_token"])

dispositivos = cargar_dispositivos()
device_names = [d.get("name", "N/A") for d in dispositivos]
device_ids = [d.get("id", {}).get("id") for d in dispositivos]

selected_device = st.selectbox("📱 Selecciona un dispositivo", device_names)
selected_id = device_ids[device_names.index(selected_device)]
DIAS = 60

# ===== CARGA DE DATOS: device_id como único argumento (no jwt) =====
@st.cache_data(ttl=1800)
def cargar_datos_dispositivo(device_id):
    return get_device_data(device_id, st.session_state["jwt_token"], days_back=DIAS)

@st.cache_data(ttl=1800)
def cargar_datos_todos(ids_tuple):  # tuple para que sea hasheable
    frames = []
    for did in ids_tuple:
        try:
            df_dev = get_device_data(did, st.session_state["jwt_token"], days_back=DIAS)
            frames.append(df_dev)
        except Exception as e:
            st.warning(f"No se pudieron cargar datos del dispositivo {did}: {e}")
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

df = cargar_datos_dispositivo(selected_id)
if df.empty:
    st.warning("No hay datos disponibles para este dispositivo")
    st.stop()

df_all = cargar_datos_todos(tuple(device_ids))  # tuple = hasheable por cache

# ===== INGENIERÍA DE CARACTERÍSTICAS =====
df["Fecha"] = df["fecha"].dt.date
df["Hora_del_Dia"] = df["fecha"].dt.hour
df["Periodo_Dia"] = pd.Categorical(
    df["Hora_del_Dia"].apply(clasificar_periodo),
    categories=ORDEN_PERIODOS,
    ordered=True
)

# ===== BATERÍA: peticiones en paralelo con ThreadPoolExecutor =====
def _fetch_battery_single(device_id):
    """Petición individual de batería — se llama en threads paralelos."""
    url = f"{TB_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries?keys=battery&limit=1"
    headers = {"X-Authorization": f"Bearer {jwt_token}"}
    try:
        r = requests.get(url, headers=headers, timeout=5)
        data = r.json()
        if "battery" not in data:
            return None
        entry = data["battery"][0]
        return {
            "device_id": device_id,
            "timestamp": pd.to_datetime(entry["ts"], unit="ms"),
            "battery": float(entry["value"])
        }
    except Exception as e:
        return None  # fallo silencioso por dispositivo individual

@st.cache_data(ttl=1800)
def cargar_bateria_paralelo(ids_tuple):
    """Lanza todas las peticiones de batería en paralelo."""
    with ThreadPoolExecutor(max_workers=min(len(ids_tuple), 10)) as executor:
        results = list(executor.map(_fetch_battery_single, ids_tuple))
    validos = [r for r in results if r is not None]
    return pd.DataFrame(validos) if validos else pd.DataFrame()

# ===== SEMÁFORO: CSS puro en lugar de matplotlib =====
def render_semaforo_css(estado_text, color_hex):
    """Círculo de estado con HTML/CSS, sin overhead de matplotlib."""
    return f"""
    <div style="text-align:center; padding: 8px 0;">
        <div style="
            width: 48px; height: 48px; border-radius: 50%;
            background: {color_hex};
            margin: 0 auto 6px;
        "></div>
        <div style="font-size: 12px; font-weight: 500; color: var(--text-color, #333);">
            {estado_text}
        </div>
    </div>
    """

# ===== SECCIÓN: ESTADO DE SENSORES =====
st.subheader("🎯 Estado de Sensores")

st.write("**Valores:**")
value_cols = st.columns(3)
for idx, key in enumerate(df["key"].unique()):
    df_key = df[df["key"] == key]
    if not df_key.empty:
        valor = float(df_key.sort_values("fecha", ascending=False).iloc[0]["value"])
        unit = PARAMETROS.get(key, {}).get("unit", "")
        label = PARAMETROS.get(key, {}).get("label", key).split("(")[0].strip()
        with value_cols[idx]:
            st.metric(label, f"{valor:.2f} {unit}")

st.write("**Indicadores:**")
circles = st.columns(3)
for idx, key in enumerate(df["key"].unique()):
    df_key = df[df["key"] == key]
    if not df_key.empty:
        valor = float(df_key.sort_values("fecha", ascending=False).iloc[0]["value"])
        estado_text, color = determinar_estado(valor, key)
        with circles[idx]:
            st.markdown(render_semaforo_css(estado_text, color), unsafe_allow_html=True)

# ===== SECCIÓN: PARÁMETROS DE REFERENCIA =====
st.subheader("📋 Parámetros de Referencia")
col1, col2, col3 = st.columns(3)
with col1:
    st.write("**Conductividad (dS/m)**")
    st.markdown("🟩 **Óptimo**: 0.2 – 1.2\n\n🟨 **Precaución**: 1.3 – 2.0\n\n🟥 **Crítico**: 2.0 – 4.0 / > 4.0")
with col2:
    st.write("**Temperatura del Suelo (°C)**")
    st.markdown("🟩 **Óptimo**: 18 – 28°C\n\n🟨 **Precaución**: 12–17 / 29–32°C\n\n🟥 **Crítico**: < 12 / > 32°C")
with col3:
    st.write("**Humedad Volumétrica (VWC %)**")
    st.markdown("🟩 **Óptimo**: 25 – 40%\n\n🟨 **Precaución**: 18–24 / 41–45%\n\n🟥 **Crítico**: < 18 / > 45%")

# ===== SECCIÓN: MÉTRICAS HISTÓRICAS =====
st.subheader("📊 Métricas Históricas")
df_sorted = df.sort_values("fecha")
tabs = st.tabs(["Temperatura", "Humedad", "Conductividad"])
historico_config = {
    "temperature": ("Temperatura Histórica", "°C", "tomato"),
    "humidity": ("Humedad Histórica", "Valor", "steelblue"),
    "soil_conductivity": ("Conductividad Histórica", "Valor", "green")
}
for tab, key in zip(tabs, ["temperature", "humidity", "soil_conductivity"]):
    with tab:
        df_key = df_sorted[df_sorted["key"] == key]
        if not df_key.empty:
            title, ylabel, color = historico_config[key]
            fig, ax = plt.subplots(figsize=(12, 5))
            ax.plot(df_key["fecha"], df_key["value"], color=color, linewidth=2)
            ax.set_title(title)
            ax.set_xlabel("Fecha")
            ax.set_ylabel(ylabel)
            plt.xticks(rotation=45)
            plt.tight_layout()
            st.pyplot(fig)
            plt.close(fig)
        else:
            st.info("No hay datos disponibles")

# ===== SECCIÓN: HEATMAPS =====
st.subheader("🕒 Variación de métrica por periodo del día")
tabs = st.tabs(["Temperatura", "Humedad", "Conductividad"])
heatmap_config = {
    "temperature": ("Temperatura del suelo", "coolwarm"),
    "humidity": ("Contenido Volumétrico", "mako"),
    "soil_conductivity": ("Conductividad aparente", "rocket_r")
}
for tab, key in zip(tabs, ["temperature", "humidity", "soil_conductivity"]):
    with tab:
        df_key = df[df["key"] == key]
        if not df_key.empty:
            df_agg = df_key.groupby(["Fecha", "Periodo_Dia"])["value"].mean().reset_index()
            pivot = df_agg.pivot(index="Periodo_Dia", columns="Fecha", values="value")
            label, cmap = heatmap_config[key]
            fig_heat, ax_heat = plt.subplots(figsize=(14, 4))
            sns.heatmap(pivot, annot=True, cmap=cmap, ax=ax_heat, cbar_kws={"label": "Valor"})
            ax_heat.set_title(f"Heatmap de {label} por Período del Día")
            plt.tight_layout()
            st.pyplot(fig_heat)
            plt.close(fig_heat)
        else:
            st.info(f"No hay datos disponibles para {heatmap_config[key][0]}")

# ===== SECCIÓN: TABLA DE DATOS =====
st.subheader("📋 Datos Detallados")
fechas_disponibles = sorted(df["Fecha"].unique(), reverse=True)
selected_date = st.selectbox("Seleccione una fecha:", fechas_disponibles, format_func=lambda x: x.strftime("%d-%m-%Y"))
df_filtered = df[df["Fecha"] == selected_date][["fecha", "key", "value"]].sort_values("fecha")
st.dataframe(df_filtered, use_container_width=True)

# ===== SECCIÓN: BATERÍA (paralelo) =====
st.subheader("🔋 Estado de Batería de Dispositivos")
df_battery = cargar_bateria_paralelo(tuple(device_ids))

if not df_battery.empty:
    now = pd.Timestamp.now()
    df_battery["diff"] = now - df_battery["timestamp"]

    def asignar_color(td):
        if td >= pd.Timedelta(days=1): return "red"
        elif td >= pd.Timedelta(hours=12): return "orange"
        elif td >= pd.Timedelta(hours=1): return "yellow"
        return "green"

    df_battery["color"] = df_battery["diff"].apply(asignar_color)
    df_battery["Porcentaje de bateria"] = df_battery["battery"] * 100

    fig_battery, ax_battery = plt.subplots(figsize=(12, 5))
    sns.swarmplot(
        data=df_battery,
        x="Porcentaje de bateria",
        hue="color",
        palette={"red": "red", "orange": "orange", "yellow": "yellow", "green": "green"},
        size=8,
        ax=ax_battery
    )
    ax_battery.set_title("Estado de Batería de Dispositivos")
    ax_battery.set_xlabel("Porcentaje de Batería (%)")
    plt.tight_layout()
    st.pyplot(fig_battery)
    plt.close(fig_battery)

    device_id_to_name = dict(zip(device_ids, device_names))
    df_battery["nombre_dispositivo"] = df_battery["device_id"].map(device_id_to_name)
    df_battery = df_battery.sort_values("battery", ascending=True)
    df_battery["battery"] = (df_battery["battery"] * 100).round()

    st.dataframe(
        df_battery[["nombre_dispositivo", "battery", "timestamp"]].rename(columns={
            "nombre_dispositivo": "Dispositivo",
            "battery": "Batería",
            "timestamp": "Última actualización"
        }),
        use_container_width=True
    )
else:
    st.info("No hay datos de batería disponibles")

# ===== SECCIÓN: ÍNDICE DE RIESGO =====
st.subheader("⚠️ Índice de Riesgo de Bloqueo Nutricional")

if not df_all.empty:
    valores_promedio = {
        key: float(df_all[df_all["key"] == key]["value"].mean())
        for key in df_all["key"].unique()
    }

    if all(k in valores_promedio for k in ("humidity", "temperature", "soil_conductivity")):
        riesgo = riesgo_bloqueo(
            hum=valores_promedio["humidity"],
            temp=valores_promedio["temperature"],
            ec=valores_promedio["soil_conductivity"]
        )
        R_score = riesgo["R_0_10"]
        nivel = "🟩 Bajo" if R_score < 3 else ("🟨 Moderado" if R_score < 6 else "🟥 Alto")

        col_main, col_details = st.columns([2, 1])
        with col_main:
            fig_r, ax_r = plt.subplots(figsize=(6, 4))
            riesgos = ["Humedad", "Temperatura", "Conductividad"]
            valores_r = [riesgo["H_risk"], riesgo["T_risk"], riesgo["EC_risk"]]
            ax_r.barh(riesgos, valores_r, color=["#3498db", "#e67e22", "#9b59b6"])
            ax_r.set_xlim(0, 1)
            ax_r.set_xlabel("Nivel de Riesgo")
            ax_r.set_title("Componentes de Riesgo de Bloqueo")
            for i, v in enumerate(valores_r):
                ax_r.text(v + 0.02, i, f"{v:.2f}", va="center", fontweight="bold")
            plt.tight_layout()
            st.pyplot(fig_r)
            plt.close(fig_r)

        with col_details:
            st.metric("Riesgo General", f"{R_score}/10", delta=nivel)
            st.markdown(f"""
            **Detalles (Promedio):**
            - Humedad: {valores_promedio['humidity']:.2f}%
            - Temperatura: {valores_promedio['temperature']:.2f}°C
            - Conductividad: {valores_promedio['soil_conductivity']:.2f} dS/m
            """)
    else:
        st.info("Datos insuficientes para calcular riesgo de bloqueo")
else:
    st.info("No se pudieron cargar datos de los dispositivos")

# ===== SECCIÓN: RECOMENDACIONES CE =====
st.subheader("💡 Recomendaciones de Conductividad Eléctrica")
df_ce = df_all[df_all["key"] == "soil_conductivity"] if not df_all.empty else pd.DataFrame()

if not df_ce.empty:
    ce_actual = float(df_ce["value"].mean())
    cat_ce = clasificar_ce(ce_actual)
    col_info, col_visual = st.columns([1, 1])

    with col_info:
        st.metric("Conductividad Actual", f"{ce_actual:.2f} dS/m")
        st.write(f"**Categoría:** {cat_ce}")
        st.info(f"📌 {recomendacion_ce(cat_ce)}")

    with col_visual:
        fig_ce, ax_ce = plt.subplots(figsize=(6, 4))
        rangos = [(0, 1.0), (1.0, 2.5), (2.5, 4.0), (4.0, 5.0)]
        categorias = ["Bajo\n(<1.0)", "Medio\n(1.0-2.5)", "Alto\n(2.5-4.0)", "Muy alto\n(>4.0)"]
        colores_cat = ["#2ecc71", "#f39c12", "#e67e22", "#e74c3c"]
        for i, (start, end) in enumerate(rangos):
            ax_ce.barh(0, end - start, left=start, height=0.5, color=colores_cat[i],
                       edgecolor="black", linewidth=2, label=categorias[i])
        ax_ce.axvline(x=ce_actual, color="blue", linestyle="--", linewidth=3, label=f"Actual: {ce_actual:.2f}")
        ax_ce.set_xlim(0, 5)
        ax_ce.set_xlabel("Conductividad (dS/m)")
        ax_ce.set_title("Clasificación de Conductividad Eléctrica")
        ax_ce.set_yticks([])
        ax_ce.legend(loc="upper right")
        plt.tight_layout()
        st.pyplot(fig_ce)
        plt.close(fig_ce)
else:
    st.info("No hay datos de conductividad disponibles")
