"""
api.py
--------
API REST simple que expone los datos de OEE Manufacturing Dashboard.

Complementa a Grafana: mientras Grafana es para visualización humana,
esta API permite que otros sistemas (una app web, otro servicio, un
script de automatización) consuman los mismos datos de forma programática.

Conecta a la misma base de datos en Neon que ya usa Grafana.

Cómo correrla localmente:
    pip install fastapi uvicorn sqlalchemy psycopg2-binary python-dotenv
    uvicorn api:app --reload

Luego abre en el navegador:
    http://127.0.0.1:8000/docs
    (documentación interactiva generada automáticamente por FastAPI)
"""

import os
from datetime import date
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()  # carga variables desde un archivo .env si existe

app = FastAPI(
    title="OEE Manufacturing API",
    description="API para consultar métricas de OEE, Takt Time y JPH de una planta simulada.",
    version="1.0.0",
)


# =========================================================
# Modelos de respuesta (Pydantic)
# Definir esto explícitamente hace que la documentación en
# /docs muestre cada campo, su tipo y su descripción — sin
# esto, Swagger solo ve un diccionario genérico.
# =========================================================

class OEEGeneral(BaseModel):
    oee: float = Field(..., description="OEE general en porcentaje (0-100)")
    disponibilidad: float = Field(..., description="Disponibilidad en porcentaje")
    rendimiento: float = Field(..., description="Rendimiento en porcentaje")
    calidad: float = Field(..., description="Calidad en porcentaje")


class OEEPorMaquina(BaseModel):
    maquina: str = Field(..., description="Nombre de la máquina")
    linea: str = Field(..., description="Línea a la que pertenece la máquina")
    oee_promedio: float = Field(..., description="OEE promedio de la máquina en porcentaje")


class CausaParada(BaseModel):
    causa: str = Field(..., description="Nombre de la causa de parada")
    categoria: str = Field(..., description="'Planeada' o 'No planeada'")
    minutos_totales: float = Field(..., description="Suma de minutos perdidos por esta causa")
    num_eventos: int = Field(..., description="Cantidad de veces que ocurrió esta causa")


class CuelloDeBotella(BaseModel):
    maquina: str = Field(..., description="Nombre de la máquina")
    linea: str = Field(..., description="Línea a la que pertenece")
    pct_cumplimiento_takt: float = Field(
        ..., description="% de días que la máquina cumplió su Takt Time objetivo (menor a 100 = cuello de botella)"
    )


class TendenciaDiaria(BaseModel):
    fecha: str = Field(..., description="Fecha en formato YYYY-MM-DD")
    oee: float = Field(..., description="OEE promedio de ese día, en porcentaje")
    disponibilidad: float = Field(..., description="Disponibilidad promedio de ese día")
    rendimiento: float = Field(..., description="Rendimiento promedio de ese día")
    calidad: float = Field(..., description="Calidad promedio de ese día")


def get_engine():
    """
    Crea la conexión a la base de datos, leyendo la connection string
    desde una variable de entorno (nunca hardcodeada en el código,
    por seguridad — sobre todo si el código se sube a GitHub).
    """
    connection_string = os.getenv("NEON_CONNECTION_STRING")
    if not connection_string:
        raise RuntimeError(
            "Falta la variable de entorno NEON_CONNECTION_STRING. "
            "Crea un archivo .env con esa variable (ver .env.example)."
        )
    if connection_string.startswith("postgresql://"):
        connection_string = connection_string.replace(
            "postgresql://", "postgresql+psycopg2://", 1
        )
    return create_engine(connection_string)


engine = None  # se inicializa en el primer request (lazy loading)


def get_conn():
    global engine
    if engine is None:
        engine = get_engine()
    return engine.connect()


@app.get("/")
def raiz():
    """Endpoint raíz — confirma que la API está viva."""
    return {
        "mensaje": "OEE Manufacturing API está corriendo.",
        "documentacion": "/docs",
    }


@app.get("/oee/general", response_model=OEEGeneral)
def oee_general(
    linea: Optional[str] = Query(None, description="Filtrar por nombre de línea"),
    maquina: Optional[str] = Query(None, description="Filtrar por nombre de máquina"),
):
    """Devuelve el OEE general y sus 3 factores, promediados en todo el histórico."""
    sql = """
        SELECT
            AVG(o.oee) * 100 AS oee,
            AVG(o.disponibilidad) * 100 AS disponibilidad,
            AVG(o.rendimiento) * 100 AS rendimiento,
            AVG(o.calidad) * 100 AS calidad
        FROM oee_turno o
        JOIN maquinas m ON o.id_maquina = m.id_maquina
        JOIN lineas l ON o.id_linea = l.id_linea
        WHERE (:linea IS NULL OR l.nombre = :linea)
          AND (:maquina IS NULL OR m.nombre = :maquina)
    """
    with get_conn() as conn:
        row = conn.execute(text(sql), {"linea": linea, "maquina": maquina}).mappings().first()
    if row is None or row["oee"] is None:
        raise HTTPException(status_code=404, detail="No hay datos para ese filtro.")
    return {k: round(v, 2) for k, v in row.items()}


@app.get("/oee/por-maquina", response_model=List[OEEPorMaquina])
def oee_por_maquina():
    """Devuelve el OEE promedio de cada máquina, ordenado de menor a mayor."""
    sql = """
        SELECT
            m.nombre AS maquina,
            l.nombre AS linea,
            AVG(o.oee) * 100 AS oee_promedio
        FROM oee_turno o
        JOIN maquinas m ON o.id_maquina = m.id_maquina
        JOIN lineas l ON o.id_linea = l.id_linea
        GROUP BY m.nombre, l.nombre
        ORDER BY oee_promedio ASC
    """
    with get_conn() as conn:
        rows = conn.execute(text(sql)).mappings().all()
    return [
        {"maquina": r["maquina"], "linea": r["linea"], "oee_promedio": round(r["oee_promedio"], 2)}
        for r in rows
    ]


@app.get("/paradas/pareto", response_model=List[CausaParada])
def pareto_causas(limite: int = Query(10, ge=1, le=50, description="Máximo de causas a devolver")):
    """Devuelve el ranking de causas de parada por minutos totales acumulados (Pareto)."""
    sql = """
        SELECT
            c.nombre AS causa,
            c.categoria,
            SUM(p.duracion_min) AS minutos_totales,
            COUNT(*) AS num_eventos
        FROM paradas p
        JOIN causas_parada c ON p.id_causa = c.id_causa
        GROUP BY c.nombre, c.categoria
        ORDER BY minutos_totales DESC
        LIMIT :limite
    """
    with get_conn() as conn:
        rows = conn.execute(text(sql), {"limite": limite}).mappings().all()
    return [
        {
            "causa": r["causa"],
            "categoria": r["categoria"],
            "minutos_totales": round(r["minutos_totales"], 1),
            "num_eventos": r["num_eventos"],
        }
        for r in rows
    ]


@app.get("/takt-jph/cuellos-de-botella", response_model=List[CuelloDeBotella])
def cuellos_de_botella():
    """
    Devuelve las máquinas que NO cumplen su Takt Time el 100% del tiempo,
    ordenadas de peor a mejor cumplimiento — identifica cuellos de botella.
    """
    sql = """
        SELECT
            m.nombre AS maquina,
            l.nombre AS linea,
            AVG(CASE WHEN t.cumple_takt THEN 100.0 ELSE 0 END) AS pct_cumplimiento
        FROM takt_jph t
        JOIN maquinas m ON t.id_maquina = m.id_maquina
        JOIN lineas l ON t.id_linea = l.id_linea
        GROUP BY m.nombre, l.nombre
        HAVING AVG(CASE WHEN t.cumple_takt THEN 100.0 ELSE 0 END) < 100
        ORDER BY pct_cumplimiento ASC
    """
    with get_conn() as conn:
        rows = conn.execute(text(sql)).mappings().all()
    return [
        {
            "maquina": r["maquina"],
            "linea": r["linea"],
            "pct_cumplimiento_takt": round(r["pct_cumplimiento"], 1),
        }
        for r in rows
    ]


@app.get("/oee/tendencia", response_model=List[TendenciaDiaria])
def oee_tendencia(
    fecha_inicio: Optional[date] = Query(None, description="Formato YYYY-MM-DD"),
    fecha_fin: Optional[date] = Query(None, description="Formato YYYY-MM-DD"),
):
    """Devuelve la tendencia diaria de OEE y sus 3 factores en un rango de fechas."""
    sql = """
        SELECT
            fecha,
            AVG(oee) * 100 AS oee,
            AVG(disponibilidad) * 100 AS disponibilidad,
            AVG(rendimiento) * 100 AS rendimiento,
            AVG(calidad) * 100 AS calidad
        FROM oee_turno
        WHERE (:fecha_inicio IS NULL OR fecha >= :fecha_inicio)
          AND (:fecha_fin IS NULL OR fecha <= :fecha_fin)
        GROUP BY fecha
        ORDER BY fecha
    """
    with get_conn() as conn:
        rows = conn.execute(
            text(sql), {"fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin}
        ).mappings().all()
    return [
        {
            "fecha": str(r["fecha"]),
            "oee": round(r["oee"], 2),
            "disponibilidad": round(r["disponibilidad"], 2),
            "rendimiento": round(r["rendimiento"], 2),
            "calidad": round(r["calidad"], 2),
        }
        for r in rows
    ]
