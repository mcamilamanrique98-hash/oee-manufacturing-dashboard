"""
generar_dimensiones.py
------------------------
Genera las tablas "maestras" (dimensiones) del modelo:
  - lineas
  - maquinas
  - turnos
  - causas_parada

Estas tablas cambian poco o nada en el tiempo, a diferencia de las tablas
de hechos (produccion_intervalos, paradas), que sí crecen turno a turno.
"""

import numpy as np
import pandas as pd

import config


def generar_lineas() -> pd.DataFrame:
    """Tabla dim: líneas de producción."""
    df = pd.DataFrame(config.LINEAS)[["id_linea", "nombre"]]
    return df


def generar_maquinas() -> pd.DataFrame:
    """
    Tabla dim: máquinas.
    Cada máquina hereda la línea a la que pertenece y una velocidad ideal
    (piezas/min) con algo de variación respecto a la velocidad base de su línea,
    para que no todas las máquinas de una línea sean idénticas.
    """
    rng = np.random.default_rng(config.RANDOM_SEED)

    filas = []
    id_maquina = 1
    for linea in config.LINEAS:
        for i in range(1, linea["n_maquinas"] + 1):
            # variación de +/-10% sobre la velocidad base de la línea
            velocidad_ideal = linea["velocidad_base"] * rng.normal(1.0, 0.10)
            filas.append({
                "id_maquina": id_maquina,
                "id_linea": linea["id_linea"],
                "nombre": f"{linea['nombre'].split(' - ')[1]} - M{i}",
                "velocidad_ideal_ppm": round(velocidad_ideal, 2),  # piezas por minuto
            })
            id_maquina += 1

    return pd.DataFrame(filas)


def generar_turnos() -> pd.DataFrame:
    """Tabla dim: turnos."""
    return pd.DataFrame(config.TURNOS)


def generar_causas_parada() -> pd.DataFrame:
    """Tabla dim: causas de parada (para el Pareto)."""
    df = pd.DataFrame(config.CAUSAS_PARADA)
    return df[["id_causa", "nombre", "categoria", "prob_relativa",
               "duracion_media_min", "duracion_sd_min"]]


def generar_todas_dimensiones() -> dict[str, pd.DataFrame]:
    """Genera y devuelve todas las tablas de dimensiones en un diccionario."""
    return {
        "lineas": generar_lineas(),
        "maquinas": generar_maquinas(),
        "turnos": generar_turnos(),
        "causas_parada": generar_causas_parada(),
    }


if __name__ == "__main__":
    dims = generar_todas_dimensiones()
    for nombre, df in dims.items():
        print(f"\n=== {nombre} ({len(df)} filas) ===")
        print(df.to_string(index=False))
