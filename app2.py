import streamlit as st
import pandas as pd
import numpy as np
import seaborn as sns
import matplotlib.pyplot as plt

# Cantidad de registros
n = 20  
np.random.seed(123)

# Rango de fechas
start_date = "01-01-2025"
end_date = "31-12-2026"

# Convertimos a datetime
start = pd.to_datetime(start_date, format="%d-%m-%Y")
end = pd.to_datetime(end_date, format="%d-%m-%Y")

# Generamos fechas aleatorias
random_dates = start + (end - start) * np.random.rand(n)
random_dates = pd.Series(random_dates)

# Generamos valores
random_values = np.random.uniform(0, 0.6, n)
VWC = np.random.uniform(0.1,0.8,n)
ca = np.random.uniform(0, 1, n)
temp = np.random.uniform(0, 30, n)
CEa = ca-VWC

#datos ambientales
Tamb= np.random.uniform(-10,40,n)
Rad = np.random.uniform(100,300,n)
Humedad = np.random.uniform(0.1,0.7,n)

# Creamos el DataFrame
df = pd.DataFrame({
    "Fecha": random_dates,
    "Contenido Volumetrico": random_values,
    "Conductividad aparente": ca,
    "Conductividad de la solucion":CEa,
    "Temperatura del suelo" : temp,
    "Temperatura ambiental":Tamb,
    "Radiacion ambiental":Rad,
    "Humedad relativa ambiental":Humedad
})
df_show = df.sort_values(by='Fecha')

#falta controles de series de tiempo

# --- INTERFAZ ---
st.title("Dashboard Permacultura Tech")

st.subheader("Metricas actuales")
sns.set_style("white")

# Tomar la fila más reciente
df_recent = df.sort_values("Fecha", ascending=False).iloc[0]

# Asegurarse de que sean floats
contenido = float(df_recent["Contenido Volumetrico"])
cond_aparente = float(df_recent["Conductividad aparente"])
cond_solucion = float(df_recent["Conductividad de la solucion"])
temp_suelo = float(df_recent["Temperatura del suelo"])

# Categorías
categorias1 = ["Contenido Volumétrico", "Conductividad aparente", "Conductividad de la solución"]

# Valores
valores1 = [contenido, cond_aparente, cond_solucion]

# Complementos
complementos1 = [1 - v for v in valores1]  

# Función semáforo
def color_semaforo(valor):
    if valor <= 0.33:
        return 'green'
    elif valor <= 0.66:
        return 'gold'
    else:
        return 'red'

colores1 = [color_semaforo(v) for v in valores1]

# Gráfico
fig1, ax1 = plt.subplots(figsize=(8, 5))

# Graficar cada barra individualmente
for i in range(len(categorias1)):
    ax1.barh(i, valores1[i], color=colores1[i], edgecolor='black')
    ax1.barh(i, complementos1[i], left=valores1[i], color='lightgray', edgecolor='black')

# Ajustar eje Y con etiquetas
ax1.set_yticks(range(len(categorias1)))
ax1.set_yticklabels(categorias1)

# Estética
ax1.set_xlim(0, 1)
ax1.set_xlabel("Valor)")

for i in range(len(categorias1)):
    # Barra principal con color semáforo
    ax1.barh(i, valores1[i], color=colores1[i], edgecolor='black')
    
    # Complemento en gris
    ax1.barh(i, complementos1[i], left=valores1[i], color='lightgray', edgecolor='black')
    
    # Texto del valor al final de la barra
    ax1.text(valores1[i] + 0.02, i, f"{valores1[i]:.2f}", va='center', fontsize=12, fontweight='bold', color=colores1[i])


# Mostrar en Streamlit
st.pyplot(fig1)


# ==============================
# FIGURA 2: Temperatura
# ==============================
categorias2 = ["Temperatura del suelo"]
valores2 = [temp_suelo]
complementos2 = [50 - temp_suelo]

fig2, ax2 = plt.subplots(figsize=(8, 2))
ax2.barh(categorias2, valores2, label="Temperatura", color="tomato")
ax2.barh(categorias2, complementos2, left=valores2, label="Complemento hasta 50°C", color="lightgray")

ax2.set_title("Temperatura del Suelo")
ax2.set_xlabel("°C (0–50)")
ax2.set_xlim(0, 50)  # Escala fija de 0 a 50
ax2.legend()

st.pyplot(fig2)


st.subheader("Metricas historicas")

# Gráfico simple con los datos
df = df.sort_values("Fecha")
X = df["Fecha"]
Y = df["Contenido Volumetrico"]

fig,ax = plt.subplots()
ax.set_title("Contenido volumetrico historico")
ax.plot(X,Y)
st.pyplot(fig)

Y = df["Temperatura del suelo"]

fig,ax = plt.subplots()
ax.set_title("Temperatura del suelo historica")
ax.plot(X,Y)
st.pyplot(fig)
Y = df["Conductividad aparente"]

fig,ax = plt.subplots()
ax.set_title("Conductividad aparente historica")
ax.plot(X,Y)
st.pyplot(fig)

# Cargar dataset
df = sns.load_dataset("iris")

# Crear columnas
col1, col2, col3 = st.columns(3)

# Gráfico 1
with col1:
    fig1, ax1 = plt.subplots()
    sns.histplot(df["sepal_length"], kde=True, ax=ax1)
    st.pyplot(fig1)

# Gráfico 2
with col2:
    fig2, ax2 = plt.subplots()
    sns.boxplot(x="species", y="petal_length", data=df, ax=ax2)
    st.pyplot(fig2)

# Gráfico 3
with col3:
    fig3, ax3 = plt.subplots()
    sns.scatterplot(x="sepal_width", y="petal_width", hue="species", data=df, ax=ax3)
    st.pyplot(fig3)


# Selector de fechas (usando selectbox para strings)
selected_date = st.selectbox("Seleccione una fecha:", df_show["Fecha"].dt.strftime("%d-%m-%Y"))

# Mostrar DataFrame filtrado
st.table(df_show[df_show["Fecha"].dt.strftime("%d-%m-%Y") == selected_date])
    