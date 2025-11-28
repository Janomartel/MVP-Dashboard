import streamlit as st
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from data_queries import init_connection, list_all_tenant_devices, get_device_data
import requests

# Configuración de página
st.set_page_config(
    page_title="Dashboard Permacultura Tech",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📊 Dashboard Permacultura Tech")

# ===== INICIALIZAR CONEXIÓN =====
try:
    jwt_token, refresh_token = init_connection()
except Exception as e:
    st.error(f"Error de conexión a ThingsBoard: {e}")
    st.stop()
    
# ===== MAPEO DE NOMBRES =====
key_mapping = {
    "temperature": "Temperatura del suelo",
    "humidity": "Contenido Volumétrico",
    "soil_conductivity": "Conductividad aparente"
}
# ===== SELECTOR DE DISPOSITIVO =====
@st.cache_data(ttl=3600)
def cargar_dispositivos():
    return list_all_tenant_devices(jwt_token)

dispositivos = cargar_dispositivos()
device_names = [d.get("name", "N/A") for d in dispositivos]
device_ids = [d.get("id", {}).get("id") for d in dispositivos]

selected_device = st.selectbox("📱 Selecciona un dispositivo", device_names)
selected_id = device_ids[device_names.index(selected_device)]

dias = 60  # Fijo a 60 días
    
# ===== CARGAR DATOS =====
@st.cache_data(ttl=1800)
def cargar_datos_dispositivo(device_id, days):
    return get_device_data(device_id, jwt_token, days_back=days)

df = cargar_datos_dispositivo(selected_id, dias)

if df.empty:
    st.warning("No hay datos disponibles para este dispositivo")
    st.stop()   
    
# ===== INGENIERÍA DE CARACTERÍSTICAS =====
df["Fecha"] = df["fecha"].dt.date
df["Hora_del_Dia"] = df["fecha"].dt.hour

def clasificar_periodo(hora):
    if 6 <= hora < 12:
        return "Mañana"
    elif 12 <= hora < 18:
        return "Tarde"
    else:
        return "Noche"

df["Periodo_Dia"] = df["Hora_del_Dia"].apply(clasificar_periodo)

# Ordenar período del día
orden_periodos = ["Mañana", "Tarde", "Noche"]
df["Periodo_Dia"] = pd.Categorical(
    df["Periodo_Dia"],
    categories=orden_periodos,
    ordered=True
)

# ===== FUNCIÓN PARA OBTENER BATERÍA =====
def get_last_battery(device_id, jwt_token, url_thingsboard):
    url = f"{url_thingsboard}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries?keys=battery&limit=1"
    headers = {"X-Authorization": f"Bearer {jwt_token}"}
    try:
        r = requests.get(url, headers=headers)
        data = r.json()
        
        if "battery" not in data:
            return None
        
        entry = data["battery"][0]
        ts = pd.to_datetime(entry["ts"], unit="ms")
        value = float(entry["value"])
        
        return {"device_id": device_id, "timestamp": ts, "battery": value}
    except Exception as e:
        st.warning(f"Error al obtener batería: {e}")
        return None
        
# ===== GRÁFICO DE BARRAS CON SEMÁFORO =====
st.subheader("🎯 Estado de Sensores")

# Definir parámetros por tipo de sensor
parametros = {
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

def determinar_estado(valor, key):
    """Determina el estado y color basado en los parámetros"""
    config = parametros.get(key, {})
    
    verde_min, verde_max = config.get("verde", (0, 0))
    amarillo_ranges = config.get("amarillo", [])
    rojo_ranges = config.get("rojo", [])
    
    if verde_min <= valor <= verde_max:
        return "Óptimo", '#2ecc71'
    
    for min_val, max_val in amarillo_ranges:
        if min_val <= valor <= max_val:
            return "Precaución", '#f39c12'
    
    for min_val, max_val in rojo_ranges:
        if min_val <= valor <= max_val:
            return "Crítico", '#e74c3c'
    
    return "Desconocido", '#95a5a6'

col_left, col_right = st.columns(2)

# Lado izquierdo - Valores del dispositivo seleccionado
with col_left:
    st.write("**Valores Actuales:**")
    for key in df["key"].unique():
        df_key = df[df["key"] == key]
        if not df_key.empty:
            valor = float(df_key.sort_values("fecha", ascending=False).iloc[0]["value"])
            label = parametros.get(key, {}).get("label", key)
            unit = parametros.get(key, {}).get("unit", "")
            st.metric(label, f"{valor:.2f} {unit}")

# Lado derecho - Círculos de color con semáforo
with col_right:
    st.write("**Estado:**")
    
    for key in df["key"].unique():
        df_key = df[df["key"] == key]
        if not df_key.empty:
            valor = float(df_key.sort_values("fecha", ascending=False).iloc[0]["value"])
            estado_text, color = determinar_estado(valor, key)
            label = parametros.get(key, {}).get("label", key)
            
            # Crear gráfico circular
            fig, ax = plt.subplots(figsize=(1, 1))
            ax.pie([1], colors=[color], startangle=90)
            ax.set_title(f"{label}\n{estado_text}", fontsize=9, fontweight='bold')
            st.pyplot(fig)

# ===== REGLAS DE REFERENCIA =====
st.subheader("📋 Parámetros de Referencia")

col1, col2, col3 = st.columns(3)

with col1:
    st.write("**Humedad Volumétrica (VWC %)**")
    st.markdown("""
    🟩 **Óptimo**: 25% – 40%
    
    🟨 **Precaución**:
    - 18% – 24% (estrés hídrico)
    - 41% – 45% (riesgo saturación)
    
    🟥 **Crítico**:
    - < 18% (estrés severo)
    - > 45% (exceso agua)
    """)

with col2:
    st.write("**Temperatura del Suelo (°C)**")
    st.markdown("""
    🟩 **Óptimo**: 18°C – 28°C
    
    🟨 **Precaución**:
    - 12°C – 17°C (frío)
    - 29°C – 32°C (calor)
    
    🟥 **Crítico**:
    - < 12°C (frío extremo)
    - > 32°C (calor extremo)
    """)

with col3:
    st.write("**Conductividad (dS/m)**")
    st.markdown("""
    🟩 **Óptimo**: 0.2 – 1.2 dS/m
    
    🟨 **Precaución**: 1.3 – 2.0 dS/m
    
    🟥 **Crítico**:
    - 2.0 – 4.0 dS/m
    - > 4.0 dS/m (muy alto)
    """)

# ===== MÉTRICAS HISTÓRICAS =====
st.subheader("📊 Métricas Históricas")

df_sorted = df.sort_values("fecha")

# Crear tabs para cada métrica
tabs = st.tabs(["Temperatura", "Humedad", "Conductividad"])

historico_config = {
    "temperature": ("temperature", "Temperatura Histórica", "°C", "tomato"),
    "humidity": ("humidity", "Humedad Histórica", "Valor", "steelblue"),
    "soil_conductivity": ("soil_conductivity", "Conductividad Histórica", "Valor", "green")
}

keys_list = ["temperature", "humidity", "soil_conductivity"]

for tab, key in zip(tabs, keys_list):
    with tab:
        df_key = df_sorted[df_sorted["key"] == key]
        
        if not df_key.empty:
            _, title, ylabel, color = historico_config[key]
            
            fig, ax = plt.subplots(figsize=(12, 5))
            ax.plot(df_key["fecha"], df_key["value"], color=color, linewidth=2)
            ax.set_title(title)
            ax.set_xlabel("Fecha")
            ax.set_ylabel(ylabel)
            plt.xticks(rotation=45)
            plt.tight_layout()
            st.pyplot(fig)
        else:
            st.info(f"No hay datos disponibles")

# ===== HEATMAPS =====
st.subheader("🔥 Heatmaps por Período del Día")

# Crear tabs para cada métrica
tabs = st.tabs(["Temperatura", "Humedad", "Conductividad"])

heatmap_config = {
    "temperature": ("Temperatura del suelo", "coolwarm"),
    "humidity": ("Contenido Volumétrico", "mako"),
    "soil_conductivity": ("Conductividad aparente", "rocket_r")
}

keys_list = ["temperature", "humidity", "soil_conductivity"]

for tab, key in zip(tabs, keys_list):
    with tab:
        df_key = df[df["key"] == key]
        
        if not df_key.empty:
            df_agg = df_key.groupby(["Fecha", "Periodo_Dia"])["value"].mean().reset_index()
            pivot = df_agg.pivot(index="Periodo_Dia", columns="Fecha", values="value")
            
            label, cmap = heatmap_config[key]
            
            fig_heat, ax_heat = plt.subplots(figsize=(14, 4))
            sns.heatmap(pivot, annot=True, cmap=cmap, ax=ax_heat, cbar_kws={'label': 'Valor'})
            ax_heat.set_title(f"Heatmap de {label} por Período del Día")
            plt.tight_layout()
            st.pyplot(fig_heat)
        else:
            st.info(f"No hay datos disponibles para {heatmap_config[key][0]}")

# ===== TABLA DE DATOS =====
st.subheader("📋 Datos Detallados")

# Selector de fechas
fechas_disponibles = sorted(df["Fecha"].unique(), reverse=True)
selected_date = st.selectbox(
    "Seleccione una fecha:",
    fechas_disponibles,
    format_func=lambda x: x.strftime("%d-%m-%Y")
)

# Mostrar DataFrame filtrado
df_filtered = df[df["Fecha"] == selected_date][["fecha", "key", "value"]].sort_values("fecha")
st.dataframe(df_filtered, use_container_width=True)

# ===== SECCIÓN DE BATERÍA =====
st.subheader("🔋 Estado de Batería de Dispositivos")

# Obtener datos de batería para todos los dispositivos
@st.cache_data(ttl=1800)
def cargar_bateria_dispositivos(device_ids, jwt_token):
    url_thingsboard = "https://tb.permaculturatech.com"  # Ajusta según tu URL
    resultados = []
    for did in device_ids:
        info = get_last_battery(did, jwt_token, url_thingsboard)
        if info:
            resultados.append(info)
    return pd.DataFrame(resultados) if resultados else pd.DataFrame()

df_battery = cargar_bateria_dispositivos(device_ids, jwt_token)

if not df_battery.empty:
    # Procesar datos de batería
    now = pd.Timestamp.now()
    df_battery["diff"] = now - df_battery["timestamp"]
    
    def asignar_color(td):
        if td >= pd.Timedelta(days=1):
            return "red"
        elif td >= pd.Timedelta(hours=12):
            return "orange"
        elif td >= pd.Timedelta(hours=1):
            return "yellow"
        else:
            return "green"
    
    df_battery["color"] = df_battery["diff"].apply(asignar_color)
    df_battery["Porcentaje de bateria"] = df_battery["battery"] * 100
    
    # Crear gráfico de swarmplot
    fig_battery, ax_battery = plt.subplots(figsize=(12, 5))
    sns.swarmplot(
        data=df_battery, 
        x="Porcentaje de bateria",
        hue="color",
        palette={
            "red": "red",
            "orange": "orange",
            "yellow": "yellow",
            "green": "green"
        },
        size=8,
        ax=ax_battery
    )
    ax_battery.set_title("Estado de Batería de Dispositivos")
    ax_battery.set_xlabel("Porcentaje de Batería (%)")
    plt.tight_layout()
    st.pyplot(fig_battery)
    
    # Tabla de batería
    # Mapear device_ids a nombres
    device_id_to_name = {did: name for did, name in zip(device_ids, device_names)}
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
