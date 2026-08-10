"""
simular_paradas.py
--------------------
Genera los eventos de parada (downtime) para cada combinación
máquina + fecha + turno.

Lógica:
  1. Para cada turno-máquina, decidir cuántas paradas hay (Poisson).
  2. Para cada parada, elegir una causa según su probabilidad relativa.
  3. Elegir una duración según la distribución de esa causa (normal truncada a valores positivos).
  4. Ubicar la parada dentro de la ventana del turno, sin salirse de los 480 min.
  5. Aplicar la anomalía visible definida en config (Máquina 5, falla mayor 5 días).

Salida: DataFrame con una fila por evento de parada.
Columnas: id_maquina, fecha, id_turno, id_causa, minuto_inicio, minuto_fin, duracion_min
(minuto_inicio/fin son minutos relativos al inicio del turno, 0-480)
"""

import numpy as np
import pandas as pd

import config


def _fecha_en_anomalia_paradas_extra(id_maquina: int, fecha) -> bool:
    """Chequea si esta máquina+fecha cae dentro de la anomalía visible de paradas extra."""
    for anomalia in config.ANOMALIAS_VISIBLES:
        if anomalia["efecto"] != "paradas_extra":
            continue
        if anomalia.get("id_maquina") != id_maquina:
            continue
        if anomalia["fecha_inicio"] <= fecha <= anomalia["fecha_fin"]:
            return True
    return False


def _elegir_causa(rng: np.random.Generator, causas_df: pd.DataFrame) -> pd.Series:
    """Elige una causa de parada según su probabilidad relativa."""
    probs = causas_df["prob_relativa"].values
    probs = probs / probs.sum()
    idx = rng.choice(causas_df.index, p=probs)
    return causas_df.loc[idx]


def _duracion_parada(rng: np.random.Generator, causa: pd.Series) -> float:
    """Genera una duración de parada (normal truncada a un mínimo de 2 min)."""
    duracion = rng.normal(causa["duracion_media_min"], causa["duracion_sd_min"])
    return max(duracion, 2.0)


def simular_paradas_turno(
    rng: np.random.Generator,
    causas_df: pd.DataFrame,
    id_maquina: int,
    fecha,
    id_turno: int,
) -> list[dict]:
    """
    Simula todas las paradas de un turno-máquina específico.
    Devuelve una lista de diccionarios (una fila por parada).
    """
    # Número base de paradas (Poisson)
    lam = config.PARADAS_POR_TURNO_LAMBDA

    # Anomalía visible: esta máquina, en estas fechas, tiene muchas más paradas
    es_anomalia = _fecha_en_anomalia_paradas_extra(id_maquina, fecha)
    if es_anomalia:
        lam = lam * 3.5  # turno casi paralizado por la falla mayor

    n_paradas = rng.poisson(lam)
    n_paradas = min(n_paradas, 15)  # límite de seguridad para no saturar el turno

    eventos = []
    minuto_cursor = 0
    duracion_turno = config.DURACION_TURNO_MIN

    for _ in range(n_paradas):
        causa = _elegir_causa(rng, causas_df)
        duracion = _duracion_parada(rng, causa)

        # separación aleatoria entre el fin de la parada anterior y el inicio de esta
        gap = rng.uniform(5, 40)
        minuto_inicio = minuto_cursor + gap

        if minuto_inicio >= duracion_turno - 2:
            break  # ya no hay espacio en el turno para más paradas

        minuto_fin = min(minuto_inicio + duracion, duracion_turno)
        duracion_real = minuto_fin - minuto_inicio

        eventos.append({
            "id_maquina": id_maquina,
            "fecha": fecha,
            "id_turno": id_turno,
            "id_causa": int(causa["id_causa"]),
            "minuto_inicio": round(minuto_inicio, 1),
            "minuto_fin": round(minuto_fin, 1),
            "duracion_min": round(duracion_real, 1),
        })

        minuto_cursor = minuto_fin

    return eventos


def generar_paradas(maquinas_df: pd.DataFrame, causas_df: pd.DataFrame) -> pd.DataFrame:
    """
    Genera la tabla completa de paradas para todas las máquinas,
    todos los días del rango configurado, y todos los turnos.
    """
    rng = np.random.default_rng(config.RANDOM_SEED)

    fechas = pd.date_range(config.FECHA_INICIO, config.FECHA_FIN, freq="D").date
    turnos_ids = [t["id_turno"] for t in config.TURNOS]

    todas_las_filas = []
    for id_maquina in maquinas_df["id_maquina"]:
        for fecha in fechas:
            for id_turno in turnos_ids:
                eventos = simular_paradas_turno(rng, causas_df, id_maquina, fecha, id_turno)
                todas_las_filas.extend(eventos)

    df = pd.DataFrame(todas_las_filas)
    df.insert(0, "id_parada", range(1, len(df) + 1))
    return df


if __name__ == "__main__":
    from generar_dimensiones import generar_maquinas, generar_causas_parada

    maquinas_df = generar_maquinas()
    causas_df = generar_causas_parada()

    paradas_df = generar_paradas(maquinas_df, causas_df)

    print(f"Total de eventos de parada generados: {len(paradas_df):,}")
    print("\nMuestra:")
    print(paradas_df.head(10).to_string(index=False))

    print("\nParadas promedio por turno-máquina:", round(
        len(paradas_df) / (len(maquinas_df) * len(config.TURNOS) *
                            (config.FECHA_FIN - config.FECHA_INICIO).days), 2
    ))

    # Verificación rápida de la anomalía visible (Máquina 5, Feb 10-14 2026)
    anomalia_mask = (
        (paradas_df["id_maquina"] == 5) &
        (paradas_df["fecha"] >= pd.to_datetime("2026-02-10").date()) &
        (paradas_df["fecha"] <= pd.to_datetime("2026-02-14").date())
    )
    print(f"\nParadas en Máquina 5 durante la anomalía (10-14 Feb 2026): {anomalia_mask.sum()}")
