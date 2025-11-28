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
# ===== SIDEBAR - SELECTOR DE DISPOSITIVO =====
with st.sidebar:
    st.header("⚙️ Configuración")
    
    @st.cache_data(ttl=3600)
    def cargar_dispositivos():
        return list_all_tenant_devices(jwt_token)
    
    dispositivos = cargar_dispositivos()
    device_names = [d.get("name", "N/A") for d in dispositivos]
    device_ids = [d.get("id", {}).get("id") for d in dispositivos]
    
    selected_device = st.selectbox("📱 Selecciona un dispositivo", device_names)
    selected_id = device_ids[device_names.index(selected_device)]
    
    # Mostrar datos del dispositivo seleccionado
    st.subheader(f"📊 {selected_device}")
    
    # Obtener último registro del dispositivo
    df_selected = cargar_datos_dispositivo(selected_id, 60)
    
    if not df_selected.empty:
        df_recent = df_selected.sort_values("fecha", ascending=False).iloc[0]
        
        for key in df_selected["key"].unique():
            df_key = df_selected[df_selected["key"] == key]
            if not df_key.empty:
                valor = float(df_key.sort_values("fecha", ascending=False).iloc[0]["value"])
                label = key_mapping.get(key, key)
                st.metric(label, f"{valor:.2f}")

    dias = 60  # Fijo a 60 días
    
# ===== GRÁFICO DE BARRAS CON SEMÁFORO =====
st.subheader("🎯 Estado de Sensores (0-1)")

# Función semáforo
def color_semaforo(valor):
    if valor <= 0.33:
        return '#2ecc71'  # Verde
    elif valor <= 0.66:
        return '#f39c12'  # Amarillo
    else:
        return '#e74c3c'  # Rojo
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
        
# Preparar datos para gráfico
keys_barra = []
valores_barra = []
colores_barra = []

for key in df["key"].unique():
    df_key = df[df["key"] == key]
    if not df_key.empty:
        valor = float(df_key.sort_values("fecha", ascending=False).iloc[0]["value"])
        # Normalizar si es necesario (si el valor está fuera de 0-1)
        valor_norm = min(max(valor / 100, 0), 1) if valor > 1 else valor
        
        keys_barra.append(key_mapping.get(key, key))
        valores_barra.append(valor_norm)
        colores_barra.append(color_semaforo(valor_norm))

# Crear gráfico de barras
fig_barras, ax_barras = plt.subplots(figsize=(10, 4))
complementos = [1 - v for v in valores_barra]

for i in range(len(keys_barra)):
    ax_barras.barh(i, valores_barra[i], color=colores_barra[i], edgecolor='black', linewidth=1.5)
    ax_barras.barh(i, complementos[i], left=valores_barra[i], color='lightgray', edgecolor='black', linewidth=1.5)
    ax_barras.text(valores_barra[i] + 0.02, i, f"{valores_barra[i]:.2f}", 
                   va='center', fontsize=10, fontweight='bold')

ax_barras.set_yticks(range(len(keys_barra)))
ax_barras.set_yticklabels(keys_barra)
ax_barras.set_xlim(0, 1)
ax_barras.set_xlabel("Valor")
ax_barras.set_title("Estado de Sensores (Escala 0-1)")
plt.tight_layout()
st.pyplot(fig_barras)

# ===== MÉTRICAS HISTÓRICAS =====
st.subheader("📊 Métricas Históricas")

# Gráficos de series de tiempo
df_sorted = df.sort_values("fecha")

col1, col2 = st.columns(2)

# Temperatura
with col1:
    df_temp = df_sorted[df_sorted["key"] == "temperature"]
    if not df_temp.empty:
        fig_temp, ax_temp = plt.subplots(figsize=(10, 4))
        ax_temp.plot(df_temp["fecha"], df_temp["value"], color='tomato', linewidth=2)
        ax_temp.set_title("Temperatura Histórica")
        ax_temp.set_xlabel("Fecha")
        ax_temp.set_ylabel("°C")
        plt.xticks(rotation=45)
        plt.tight_layout()
        st.pyplot(fig_temp)

# Humedad
with col2:
    df_hum = df_sorted[df_sorted["key"] == "humidity"]
    if not df_hum.empty:
        fig_hum, ax_hum = plt.subplots(figsize=(10, 4))
        ax_hum.plot(df_hum["fecha"], df_hum["value"], color='steelblue', linewidth=2)
        ax_hum.set_title("Humedad Histórica")
        ax_hum.set_xlabel("Fecha")
        ax_hum.set_ylabel("Valor")
        plt.xticks(rotation=45)
        plt.tight_layout()
        st.pyplot(fig_hum)

# Conductividad
df_cond = df_sorted[df_sorted["key"] == "soil_conductivity"]
if not df_cond.empty:
    fig_cond, ax_cond = plt.subplots(figsize=(10, 4))
    ax_cond.plot(df_cond["fecha"], df_cond["value"], color='green', linewidth=2)
    ax_cond.set_title("Conductividad Histórica")
    ax_cond.set_xlabel("Fecha")
    ax_cond.set_ylabel("Valor")
    plt.xticks(rotation=45)
    plt.tight_layout()
    st.pyplot(fig_cond)

# ===== HEATMAPS =====
st.subheader("🔥 Heatmaps por Período del Día")

# Agregar datos por Fecha + Período del Día
for key in df["key"].unique():
    df_key = df[df["key"] == key]
    
    if not df_key.empty:
        df_agg = df_key.groupby(["Fecha", "Periodo_Dia"])["value"].mean().reset_index()
        pivot = df_agg.pivot(index="Periodo_Dia", columns="Fecha", values="value")
        
        # Seleccionar colormap según el tipo de dato
        if key == "temperature":
            cmap = "coolwarm"
        elif key == "humidity":
            cmap = "mako"
        else:
            cmap = "rocket_r"
        
        fig_heat, ax_heat = plt.subplots(figsize=(14, 4))
        sns.heatmap(pivot, annot=False, cmap=cmap, ax=ax_heat, cbar_kws={'label': 'Valor'})
        ax_heat.set_title(f"Heatmap de {key_mapping.get(key, key)} por Período del Día")
        plt.tight_layout()
        st.pyplot(fig_heat)

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
