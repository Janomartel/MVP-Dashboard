import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from adjustText import adjust_text
import matplotlib.ticker as mticker
import datetime

# =========================
# Dashboard Permacultura Tech
# =========================

# ----------------------
# Título
# ----------------------
st.title("Dashboard Permacultura Tech")
st.subheader("Esquema General")

# ----------------------
# Generación de datos de ejemplo
# ----------------------
n = 20  
np.random.seed(123)

start_date = "01-01-2025"
end_date = "31-12-2026"

start = pd.to_datetime(start_date, format="%d-%m-%Y")
end = pd.to_datetime(end_date, format="%d-%m-%Y")

random_dates = start + (end - start) * np.random.rand(n)
random_dates = pd.Series(random_dates)

random_values = np.random.uniform(0, 0.6, n)
VWC = np.random.uniform(0.1,0.8,n)
ca = np.random.uniform(0, 1, n)
temp = np.random.uniform(0, 30, n)
CEa = ca-VWC

Tamb= np.random.uniform(-10,40,n)
Rad = np.random.uniform(100,300,n)
Humedad = np.random.uniform(0.1,0.7,n)
Humedad_f = np.random.uniform(0.1,0.7,n)

df = pd.DataFrame({
    "Fecha": random_dates,
    "Contenido Volumetrico": random_values,
    "Conductividad aparente": ca,
    "Conductividad de la solucion":CEa,
    "Temperatura del suelo" : temp,
    "Temperatura ambiental":Tamb,
    "Radiacion ambiental":Rad,
    "Humedad relativa ambiental":Humedad,
    "Necesidades hidricas futuras":Humedad_f
})

df_show = df.sort_values(by='Fecha')

# =========================
# Inputs de fecha arriba (DD-MM-YYYY)
# =========================

# col1, col2 = st.columns(2)

# with col1:
#     start_str = st.text_input("Fecha inicio (DD-MM-YYYY):", "01-01-2024")
# with col2:
#     end_str = st.text_input("Fecha fin (DD-MM-YYYY):", "31-12-2027")

# # Convertir a datetime
# try:
#     start_date_input = pd.to_datetime(start_str, format="%d-%m-%Y")
#     end_date_input = pd.to_datetime(end_str, format="%d-%m-%Y")
# except:
#     st.error("Formato de fecha incorrecto. Debe ser DD-MM-YYYY")
#     st.stop()


min_date = df_show["Fecha"].min().date()
max_date = df_show["Fecha"].max().date()

col1, col2 = st.columns(2)

with col1:
    start_date_input = st.date_input(
        "Fecha inicio", 
        value=min_date, 
        min_value=min_date, 
        max_value=max_date
    )

with col2:
    end_date_input = st.date_input(
        "Fecha fin", 
        value=max_date, 
        min_value=min_date, 
        max_value=max_date
    )

# Convertimos a datetime
start_date_input = pd.to_datetime(start_date_input)
end_date_input = pd.to_datetime(end_date_input)

# hasta aqui

# Filtrar DataFrame según rango
df_filtered = df_show[
    (df_show["Fecha"] >= start_date_input) & 
    (df_show["Fecha"] <= end_date_input)
]
# =========================
# Generar eventos recurrentes (~cada 2 semanas)
# =========================
tipos_eventos = ["Riego", "Fertilización", "Planificación de riego"]
markers = {"Riego": "o", "Fertilización": "s", "Planificación de riego": "^"}
colors = {"Riego": "blue", "Fertilización": "green", "Planificación de riego": "purple"}

# Crear fechas cada 14 días en el rango
rango_fechas = pd.date_range(start=start_date_input, end=end_date_input, freq="14D")

eventos = []
for fecha in rango_fechas:
    for tipo in tipos_eventos:
        # Buscar la fila de df_filtered más cercana a la fecha
        fila = df_filtered.iloc[(df_filtered["Fecha"] - fecha).abs().argsort()[:1]]
        fila = fila.copy()
        fila["Tipo"] = tipo
        eventos.append(fila)

df_eventos = pd.concat(eventos).reset_index(drop=True)

# =========================
# Selector de eventos
# =========================
selected_eventos = st.multiselect(
    "Selecciona eventos a mostrar:",
    options=tipos_eventos,
    default=tipos_eventos  # por defecto todos
)

# =========================
# Gráfico
# =========================
graph_placeholder = st.empty()

selected_var = st.selectbox("Selecciona una variable:", df.columns[1:], index=0)

today = pd.to_datetime(datetime.date.today())
df_past = df_filtered[df_filtered["Fecha"] <= today]
df_future = df_filtered[df_filtered["Fecha"] > today]

fig, ax = plt.subplots()

df_plot = df_filtered.sort_values("Fecha")

# Línea histórica
sns.lineplot(
    data=df_plot[df_plot["Fecha"] <= today], 
    x="Fecha", 
    y=selected_var, 
    ax=ax, 
    color="blue",
    label="Histórico"
)

# Línea de predicción (futura)
sns.lineplot(
    data=df_plot[df_plot["Fecha"] > today],
    x="Fecha", 
    y=selected_var, 
    ax=ax, 
    color="orange", 
    linestyle="--",
    label="Predicción"
)

# Líneas horizontales de referencia
ymin = df_filtered[selected_var].min()
ymax = df_filtered[selected_var].max()
ax.axhline(y=ymin, color="red", linestyle="--", linewidth=1, label=f"Mínimo ({ymin:.2f})")
ax.axhline(y=ymax, color="red", linestyle="--", linewidth=1, label=f"Máximo ({ymax:.2f})")

# =========================
# Graficar eventos filtrados
# =========================
for tipo in selected_eventos:
    subset = df_eventos[df_eventos["Tipo"] == tipo]
    ax.scatter(
        subset["Fecha"], subset[selected_var],
        color=colors[tipo],
        marker=markers[tipo],
        s=70,
        label=tipo
    )

# =========================
# Configuración general
# =========================
ax.set_title(f"Gráfico de {selected_var}")
ax.set_xlabel("Fecha")
ax.set_ylabel(selected_var)
ax.set_xlim(start_date_input, end_date_input)
ax.tick_params(axis="x", labelsize=8)
plt.setp(ax.get_xticklabels(), rotation=30, ha="right")

# =========================
# Leyenda consolidada
# =========================
# Combinar leyenda de líneas + eventos sin duplicados
handles, labels = ax.get_legend_handles_labels()
by_label = dict(zip(labels, handles))
ax.legend(by_label.values(), by_label.keys(), title="Leyenda", loc="upper right", fontsize=6)


graph_placeholder.pyplot(fig)
















# Segundo grafico

# Datos de ejemplo
n = 100
now = pd.Timestamp.now()

# --- 90% de puntos en últimas 24h (sesgo hacia <1h) ---
n_recent = int(n * 0.95)
deltas_recent = np.random.exponential(scale=3*3600, size=n_recent)  # en segundos
deltas_recent = np.clip(deltas_recent, 0, 24*3600)

# --- 10% de puntos hasta 7 días atrás ---
n_old = n - n_recent
deltas_old = np.random.uniform(24*3600, 7*24*3600, size=n_old)  # entre 1 y 7 días

# Concatenar todos los deltas
deltas = np.concatenate([deltas_recent, deltas_old])

# Restar esos deltas a "ahora"
f = now - pd.to_timedelta(deltas, unit="s")

# Batería
bateria = np.round(np.random.uniform(0, 1, n), 2)

# DataFrame final
df = pd.DataFrame({
    'fecha_hora': f,
    'bateria': bateria
})
df["identificador"] = [f"P{i}" for i in range(len(df))]

# --- Clasificación por color ---
diff = now - df["fecha_hora"]

def asignar_color(td):
    if td >= pd.Timedelta(days=1):
        return "red"      # >= 1 día
    elif td >= pd.Timedelta(hours=12):
        return "orange"   # entre 12h y 1d
    elif td >= pd.Timedelta(hours=1):
        return "yellow"   # entre 1h y 12h
    else:
        return "green"    # < 1h
    
legend_labels = {
    "red": "≥ 1 día",
    "orange": "12h – 1 día",
    "yellow": "1h – 12h",
    "green": "< 1h"
}

df["color"] = diff.apply(asignar_color)

# --- Gráfico en Streamlit ---
st.subheader("Estado sensores")
graph_placeholder = st.empty()

# Crear columna en porcentaje para graficar
df["Porcentaje de bateria"] = df["bateria"] * 100

# --- Gráfico en Streamlit ---
fig, ax = plt.subplots()

sns.swarmplot(
    data=df, 
    x="Porcentaje de bateria",  # Usar columna en %
    hue="color", 
    palette={
        "red": "red", 
        "orange": "orange", 
        "yellow": "yellow", 
        "green": "green"
    }, 
    size=6, ax=ax
)

# Ajustes de ejes y título
ax.set_yticks([])
ax.set_ylabel("")
ax.set_title("Estado de baterías (%)")

# Leyenda ordenada
handles, labels = ax.get_legend_handles_labels()
ordered_handles = [handles[labels.index(color)] for color in legend_labels.keys()]
ordered_labels = [legend_labels[color] for color in legend_labels.keys()]
ax.legend(ordered_handles, ordered_labels, title="Estado", bbox_to_anchor=(1.01, 1), loc="upper left")

# Eje X en formato %
ax.xaxis.set_major_formatter(lambda x, _: f'{int(x)}%')

graph_placeholder.pyplot(fig)

#Filtrar solo los rojos
df_red = df[df["color"] == "red"]

# Ordenar de menor a mayor batería
df_red_sorted = df_red.sort_values("bateria", ascending=True)

# Mantener solo identificador y batería (o más columnas si quieres)
df_red_sorted = df_red_sorted[["identificador", "bateria"]].reset_index(drop=True)
df_red_sorted["bateria"] = df_red_sorted["bateria"] * 100

# Mostrar en Streamlit como tabla
st.subheader(f"Baterias con ultimo reporte de 1 día o más \n (menor → mayor)")
st.dataframe(df_red_sorted)
