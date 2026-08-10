"""
config.py
----------
Configuración central del proyecto OEE Manufacturing Dashboard.
Todos los parámetros de escala, fechas y reglas de simulación viven acá,
para que sea fácil ajustar el tamaño del dataset sin tocar la lógica.
"""

from datetime import date

# -----------------------------
# Reproducibilidad
# -----------------------------
RANDOM_SEED = 42

# -----------------------------
# Rango de tiempo a simular
# -----------------------------
FECHA_INICIO = date(2025, 8, 1)
FECHA_FIN = date(2026, 7, 28)  # ~12 meses de histórico

# -----------------------------
# Estructura de líneas y máquinas
# -----------------------------
# Cada línea tiene un número de máquinas y un "perfil" de velocidad ideal
# (piezas por minuto) que varía un poco entre máquinas de la misma línea.
LINEAS = [
    {"id_linea": 1, "nombre": "Línea 1 - Ensamblaje", "n_maquinas": 4, "velocidad_base": 45},
    {"id_linea": 2, "nombre": "Línea 2 - Empaque", "n_maquinas": 4, "velocidad_base": 60},
    {"id_linea": 3, "nombre": "Línea 3 - Moldeo", "n_maquinas": 4, "velocidad_base": 35},
]
# Total: 12 máquinas (ajustable agregando líneas o subiendo n_maquinas)

# -----------------------------
# Turnos
# -----------------------------
TURNOS = [
    {"id_turno": 1, "nombre": "Mañana", "hora_inicio": "06:00", "hora_fin": "14:00"},
    {"id_turno": 2, "nombre": "Tarde", "hora_inicio": "14:00", "hora_fin": "22:00"},
    {"id_turno": 3, "nombre": "Noche", "hora_inicio": "22:00", "hora_fin": "06:00"},
]
DURACION_TURNO_MIN = 8 * 60  # 480 min

# -----------------------------
# Causas de parada
# -----------------------------
# probabilidad relativa = qué tan frecuente es esa causa (para el Pareto)
# duracion_media_min / duracion_sd_min = parámetros de la distribución de duración
CAUSAS_PARADA = [
    {"id_causa": 1, "nombre": "Cambio de formato",       "categoria": "Planeada",     "prob_relativa": 0.20, "duracion_media_min": 25, "duracion_sd_min": 8},
    {"id_causa": 2, "nombre": "Mantenimiento programado", "categoria": "Planeada",     "prob_relativa": 0.10, "duracion_media_min": 45, "duracion_sd_min": 15},
    {"id_causa": 3, "nombre": "Falla mecánica",            "categoria": "No planeada",  "prob_relativa": 0.15, "duracion_media_min": 40, "duracion_sd_min": 20},
    {"id_causa": 4, "nombre": "Falta de material",         "categoria": "No planeada",  "prob_relativa": 0.15, "duracion_media_min": 20, "duracion_sd_min": 10},
    {"id_causa": 5, "nombre": "Ajuste de calidad",         "categoria": "No planeada",  "prob_relativa": 0.15, "duracion_media_min": 12, "duracion_sd_min": 5},
    {"id_causa": 6, "nombre": "Falta de operador",         "categoria": "No planeada",  "prob_relativa": 0.10, "duracion_media_min": 15, "duracion_sd_min": 6},
    {"id_causa": 7, "nombre": "Microparada / atasco",      "categoria": "No planeada",  "prob_relativa": 0.15, "duracion_media_min": 6,  "duracion_sd_min": 3},
]

# -----------------------------
# Parámetros de simulación de paradas
# -----------------------------
PARADAS_POR_TURNO_LAMBDA = 4  # media de una distribución de Poisson

# -----------------------------
# Parámetros de producción
# -----------------------------
INTERVALO_PRODUCCION_MIN = 20   # cada cuántos minutos se registra un "pulso" de producción
RUIDO_VELOCIDAD_SD = 0.08       # variabilidad normal de velocidad real vs ideal (8%)
TASA_RECHAZO_BASE = 0.025       # 2.5% de piezas rechazadas en condiciones normales
TASA_RECHAZO_SD = 0.01

# -----------------------------
# Anomalías
# -----------------------------
# Visibles: eventos claros y explicables (para contar la historia en una entrevista)
ANOMALIAS_VISIBLES = [
    {
        "descripcion": "Falla mayor en Máquina 5 (Línea 2) - 5 días de paradas constantes",
        "id_maquina": 5,
        "fecha_inicio": date(2026, 2, 10),
        "fecha_fin": date(2026, 2, 14),
        "efecto": "paradas_extra",
    },
    {
        "descripcion": "Pico de rechazos en Línea 3 por lote de material defectuoso",
        "id_linea": 3,
        "fecha_inicio": date(2025, 11, 3),
        "fecha_fin": date(2025, 11, 6),
        "efecto": "rechazo_alto",
    },
]

# Sutiles: degradación gradual, sin causa registrada (para descubrir analizando tendencias)
ANOMALIAS_SUTILES = [
    {
        "descripcion": "Degradación gradual de rendimiento en Máquina 9 (Línea 3) por falta de mantenimiento",
        "id_maquina": 9,
        "fecha_inicio": date(2026, 4, 1),
        "fecha_fin": FECHA_FIN,
        "efecto": "degradacion_gradual",
    },
]

# -----------------------------
# Takt Time / JPH (Fase B — alineado a terminología de Ingeniería Industrial)
# -----------------------------
# Factor de utilización objetivo: qué % de la capacidad teórica máxima se
# fija como "demanda" a cumplir. 85% es un valor típico en la industria
# (nadie planea al 100%, siempre se deja margen para variabilidad normal).
FACTOR_UTILIZACION_OBJETIVO = 0.85

# Minutos disponibles por día (3 turnos completos)
MINUTOS_DISPONIBLES_DIA = DURACION_TURNO_MIN * len(TURNOS)

# -----------------------------
# Conexión a PostgreSQL
# -----------------------------
# Se recomienda usar variables de entorno en vez de hardcodear credenciales.
DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "oee_dashboard",
    "user": "postgres",
    "password": None,  # se toma de variable de entorno PGPASSWORD o .env
}
