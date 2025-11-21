from datetime import datetime, timedelta
import requests
import pandas as pd
import logging
import streamlit as st

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Configuración desde Streamlit Secrets
TB_URL = st.secrets["TB_URL"]
TB_USERNAME = st.secrets["TB_USERNAME"]
TB_PASSWORD = st.secrets["TB_PASSWORD"]
TB_KEYS = st.secrets.get("TB_KEYS", "temperature,humidity,soil_conductivity")
TB_LIMIT = st.secrets.get("TB_LIMIT", "500")
TB_DAYS_BACK = int(st.secrets.get("TB_DAYS_BACK", "60"))

# Variables globales para tokens
_jwt_token = None
_refresh_token = None


def login(username: str = None, password: str = None) -> tuple[str, str]:
    """
    Autentica en ThingsBoard y obtiene tokens JWT.
    
    Args:
        username: Usuario de ThingsBoard (usa env var si no se proporciona)
        password: Contraseña de ThingsBoard (usa env var si no se proporciona)
    
    Returns:
        tuple: (jwt_token, refresh_token)
    """
    global _jwt_token, _refresh_token
    
    username = username or TB_USERNAME
    password = password or TB_PASSWORD
    
    payload = {
        "username": username,
        "password": password
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(f"{TB_URL}/api/auth/login", json=payload, headers=headers)
        response.raise_for_status()
        
        _jwt_token = response.json()["token"]
        _refresh_token = response.json()["refreshToken"]
        
        logging.info(f"Autenticación exitosa para usuario: {username}")
        return _jwt_token, _refresh_token
        
    except requests.exceptions.HTTPError as http_err:
        logging.error(f"Error HTTP en login: {http_err}")
        raise
    except Exception as err:
        logging.error(f"Error inesperado en login: {err}")
        raise


def reauth_token(jwt_token: str, refresh_token: str) -> tuple[str, str]:
    """
    Refresca los tokens JWT usando el refresh_token.
    
    Args:
        jwt_token: Token JWT actual
        refresh_token: Token de refresco
    
    Returns:
        tuple: (nuevo_jwt_token, nuevo_refresh_token)
    """
    global _jwt_token, _refresh_token
    
    payload = {
        "refreshToken": refresh_token
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-Authorization": f"Bearer {jwt_token}"
    }
    
    try:
        response = requests.post(
            f"{TB_URL}/api/auth/token",
            json=payload,
            headers=headers
        )
        response.raise_for_status()
        
        _jwt_token = response.json()["token"]
        _refresh_token = response.json()["refreshToken"]
        
        logging.info("Tokens refrescados exitosamente")
        return _jwt_token, _refresh_token
        
    except Exception as err:
        logging.error(f"Error al refrescar tokens: {err}")
        raise


def list_all_tenant_devices(jwt_token: str, page_size: int = 100) -> list:
    """
    Lista todos los dispositivos del tenant con paginación.
    
    Args:
        jwt_token: Token JWT de autenticación
        page_size: Tamaño de página para paginación
    
    Returns:
        list: Lista de dispositivos
    """
    all_devices = []
    page = 0
    has_next = True
    
    headers = {
        "Accept": "application/json",
        "X-Authorization": f"Bearer {jwt_token}"
    }
    
    logging.info("Iniciando obtención de dispositivos...")
    
    while has_next:
        list_url = f"{TB_URL}/api/tenant/deviceInfos?pageSize={page_size}&page={page}"
        
        try:
            response = requests.get(list_url, headers=headers)
            response.raise_for_status()
            
            page_data = response.json()
            
            if page_data.get("data"):
                all_devices.extend(page_data["data"])
                logging.info(f"Página {page}: {len(page_data['data'])} dispositivos obtenidos")
            
            has_next = page_data.get("hasNext", False)
            page += 1
            
        except requests.exceptions.HTTPError as http_err:
            logging.error(f"Error HTTP en página {page}: {http_err}")
            break
        except Exception as err:
            logging.error(f"Error inesperado al listar dispositivos: {err}")
            break
    
    logging.info(f"Total de dispositivos obtenidos: {len(all_devices)}")
    return all_devices


def get_device_access_token(device_id: str, jwt_token: str) -> dict:
    """
    Obtiene el token de acceso de un dispositivo.
    
    Args:
        device_id: ID del dispositivo
        jwt_token: Token JWT de autenticación
    
    Returns:
        dict: Credenciales del dispositivo
    """
    headers = {
        "X-Authorization": f"Bearer {jwt_token}"
    }
    
    try:
        response = requests.get(
            f"{TB_URL}/api/device/{device_id}/credentials",
            headers=headers
        )
        response.raise_for_status()
        return response.json()
        
    except Exception as err:
        logging.error(f"Error al obtener token del dispositivo {device_id}: {err}")
        raise


def get_telemetry_data(
    device_id: str,
    jwt_token: str,
    keys: str = None,
    days_back: int = None,
    limit: str = None
) -> dict:
    """
    Obtiene datos de telemetría de un dispositivo.
    
    Args:
        device_id: ID del dispositivo
        jwt_token: Token JWT de autenticación
        keys: Claves de telemetría (comma-separated)
        days_back: Días hacia atrás para la consulta
        limit: Límite de puntos de datos
    
    Returns:
        dict: Datos de telemetría en formato {clave: [valores]}
    """
    keys = keys or TB_KEYS
    days_back = days_back or TB_DAYS_BACK
    limit = limit or TB_LIMIT
    
    # Calcular timestamps
    start_date = datetime.now() - timedelta(days=days_back)
    start_ts = str(int(start_date.timestamp() * 1000))
    end_date = datetime.now()
    end_ts = str(int(end_date.timestamp() * 1000))
    
    headers = {
        "Accept": "application/json",
        "X-Authorization": f"Bearer {jwt_token}"
    }
    
    url = (
        f"{TB_URL}/api/plugins/telemetry/DEVICE/{device_id}/values/timeseries"
        f"?keys={keys}&startTs={start_ts}&endTs={end_ts}&limit={limit}"
    )
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        logging.info(f"Telemetría obtenida para dispositivo {device_id}")
        return response.json()
        
    except Exception as err:
        logging.error(f"Error al obtener telemetría del dispositivo {device_id}: {err}")
        raise


def parse_telemetry_to_dataframe(data: dict) -> pd.DataFrame:
    """
    Convierte datos de telemetría en un DataFrame de pandas.
    
    Args:
        data: Diccionario con datos de telemetría {clave: [valores]}
    
    Returns:
        pd.DataFrame: DataFrame con columnas ts, value, key, fecha
    """
    dfs = []
    
    for key, values in data.items():
        # Asegurar tipos correctos
        for v in values:
            v["ts"] = int(v["ts"])
            v["value"] = float(v["value"])
        
        df_key = pd.DataFrame(values)
        df_key["key"] = key
        dfs.append(df_key)
    
    # Concatenar todos los DataFrames
    df = pd.concat(dfs, ignore_index=True)
    df["fecha"] = pd.to_datetime(df["ts"], unit="ms")
    
    logging.info(f"DataFrame creado con {len(df)} registros")
    return df.sort_values("fecha").reset_index(drop=True)


def get_device_data(device_id: str, jwt_token: str, days_back: int = None) -> pd.DataFrame:
    """
    Función de conveniencia: obtiene telemetría y la convierte en DataFrame.
    
    Args:
        device_id: ID del dispositivo
        jwt_token: Token JWT de autenticación
        days_back: Días hacia atrás para la consulta
    
    Returns:
        pd.DataFrame: Datos de telemetría procesados
    """
    telemetry_data = get_telemetry_data(
        device_id=device_id,
        jwt_token=jwt_token,
        days_back=days_back
    )
    
    return parse_telemetry_to_dataframe(telemetry_data)


def get_all_devices_data(jwt_token: str, days_back: int = None) -> dict:
    """
    Obtiene datos de telemetría de TODOS los dispositivos.
    
    Args:
        jwt_token: Token JWT de autenticación
        days_back: Días hacia atrás para la consulta
    
    Returns:
        dict: {device_id: DataFrame}
    """
    devices = list_all_tenant_devices(jwt_token)
    device_ids = [device.get("id", {}).get("id") for device in devices if device.get("id")]
    
    all_data = {}
    
    for device_id in device_ids:
        try:
            df = get_device_data(device_id, jwt_token, days_back)
            all_data[device_id] = df
            logging.info(f"Datos obtenidos para dispositivo {device_id}")
        except Exception as err:
            logging.error(f"No se pudieron obtener datos para {device_id}: {err}")
            continue
    
    return all_data


# Función auxiliar para inicializar la conexión
def init_connection():
    """Inicializa la conexión con ThingsBoard."""
    global _jwt_token, _refresh_token
    
    if not _jwt_token:
        _jwt_token, _refresh_token = login()
    
    return _jwt_token, _refresh_token
