"""
simular_produccion.py
------------------------
Genera los "pulsos" de producción de cada máquina, en intervalos cortos
(config.INTERVALO_PRODUCCION_MIN, ej: cada 20 min) dentro del tiempo que
la máquina estuvo REALMENTE operando (turno menos las paradas ya simuladas).

Lógica por cada turno-máquina:
  1. Tomar el tiempo operando = 480 min - suma(duración de paradas de ese turno)
  2. Dividir ese tiempo operando en intervalos de ~20 min
  3. Para cada intervalo:
       a. velocidad_real = velocidad_ideal * ruido_normal(1.0, RUIDO_VELOCIDAD_SD)
          (con ajuste si aplica la anomalía sutil de degradación gradual)
       b. piezas_totales = velocidad_real * minutos_del_intervalo
       c. tasa_rechazo = TASA_RECHAZO_BASE +/- variabilidad
          (con ajuste si aplica la anomalía visible de rechazo alto)
       d. piezas_rechazadas = piezas_totales * tasa_rechazo
       e. piezas_buenas = piezas_totales - piezas_rechazadas

Salida: DataFrame con una fila por intervalo de producción.
Columnas: id_maquina, fecha, id_turno, minuto_inicio, minuto_fin,
          piezas_totales, piezas_buenas, piezas_rechazadas
"""

import numpy as np
import pandas as pd

import config


def _tiempo_operando_por_turno(paradas_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula, para cada combinación (id_maquina, fecha, id_turno), la suma de
    minutos perdidos en paradas. Sirve para saber cuánto tiempo quedó
    disponible para producir.
    """
    resumen = (
        paradas_df
        .groupby(["id_maquina", "fecha", "id_turno"])["duracion_min"]
        .sum()
        .reset_index()
        .rename(columns={"duracion_min": "minutos_parada"})
    )
    return resumen


def _factor_degradacion(id_maquina: int, fecha) -> float:
    """
    Anomalía sutil: degradación gradual de rendimiento en una máquina
    específica, sin causa de parada asociada (para descubrir analizando
    tendencias, no por un evento marcado).
    Devuelve un multiplicador de velocidad (1.0 = sin degradación).
    """
    for anomalia in config.ANOMALIAS_SUTILES:
        if anomalia["efecto"] != "degradacion_gradual":
            continue
        if anomalia.get("id_maquina") != id_maquina:
            continue
        if anomalia["fecha_inicio"] <= fecha <= anomalia["fecha_fin"]:
            # entre más avanzado el período, mayor la degradación (hasta -25%)
            dias_transcurridos = (fecha - anomalia["fecha_inicio"]).days
            duracion_total = (anomalia["fecha_fin"] - anomalia["fecha_inicio"]).days
            progreso = min(dias_transcurridos / max(duracion_total, 1), 1.0)
            return 1.0 - (0.25 * progreso)
    return 1.0


def _factor_rechazo_alto(id_linea: int, fecha) -> float:
    """
    Anomalía visible: pico de rechazos en una línea completa por un lote
    de material defectuoso. Devuelve un multiplicador sobre la tasa de rechazo.
    """
    for anomalia in config.ANOMALIAS_VISIBLES:
        if anomalia["efecto"] != "rechazo_alto":
            continue
        if anomalia.get("id_linea") != id_linea:
            continue
        if anomalia["fecha_inicio"] <= fecha <= anomalia["fecha_fin"]:
            return 4.0  # la tasa de rechazo se cuadruplica durante el incidente
    return 1.0


def simular_produccion_turno(
    rng: np.random.Generator,
    id_maquina: int,
    id_linea: int,
    velocidad_ideal: float,
    fecha,
    id_turno: int,
    minutos_parada: float,
) -> list[dict]:
    """Simula todos los intervalos de producción de un turno-máquina."""
    tiempo_operando = max(config.DURACION_TURNO_MIN - minutos_parada, 0)

    intervalo = config.INTERVALO_PRODUCCION_MIN
    n_intervalos_completos = int(tiempo_operando // intervalo)
    resto = tiempo_operando % intervalo

    duraciones_intervalos = [intervalo] * n_intervalos_completos
    if resto > 0:
        duraciones_intervalos.append(resto)

    factor_degradacion = _factor_degradacion(id_maquina, fecha)
    factor_rechazo = _factor_rechazo_alto(id_linea, fecha)

    filas = []
    minuto_cursor = 0.0
    for dur_min in duraciones_intervalos:
        # a) velocidad real con ruido natural + degradación si aplica
        ruido = rng.normal(1.0, config.RUIDO_VELOCIDAD_SD)
        velocidad_real = velocidad_ideal * ruido * factor_degradacion
        velocidad_real = max(velocidad_real, 0)

        # b) piezas totales del intervalo
        piezas_totales = velocidad_real * dur_min

        # c) tasa de rechazo del intervalo (con variabilidad + anomalía)
        tasa_rechazo = rng.normal(config.TASA_RECHAZO_BASE, config.TASA_RECHAZO_SD)
        tasa_rechazo = np.clip(tasa_rechazo, 0, 0.5) * factor_rechazo
        tasa_rechazo = min(tasa_rechazo, 1.0)

        # d) y e) piezas buenas / rechazadas
        piezas_rechazadas = piezas_totales * tasa_rechazo
        piezas_buenas = piezas_totales - piezas_rechazadas

        filas.append({
            "id_maquina": id_maquina,
            "fecha": fecha,
            "id_turno": id_turno,
            "minuto_inicio": round(minuto_cursor, 1),
            "minuto_fin": round(minuto_cursor + dur_min, 1),
            "piezas_totales": round(piezas_totales, 2),
            "piezas_buenas": round(piezas_buenas, 2),
            "piezas_rechazadas": round(piezas_rechazadas, 2),
        })

        minuto_cursor += dur_min

    return filas


def generar_produccion(maquinas_df: pd.DataFrame, paradas_df: pd.DataFrame) -> pd.DataFrame:
    """
    Genera la tabla completa de producción (intervalos) para todas las
    máquinas, todos los días y turnos configurados.
    """
    rng = np.random.default_rng(config.RANDOM_SEED + 1)  # semilla distinta a paradas

    tiempo_parada_df = _tiempo_operando_por_turno(paradas_df)
    fechas = pd.date_range(config.FECHA_INICIO, config.FECHA_FIN, freq="D").date
    turnos_ids = [t["id_turno"] for t in config.TURNOS]

    # índice rápido de minutos de parada por (maquina, fecha, turno)
    tiempo_parada_idx = tiempo_parada_df.set_index(["id_maquina", "fecha", "id_turno"])["minutos_parada"]

    todas_las_filas = []
    for _, maquina in maquinas_df.iterrows():
        id_maquina = maquina["id_maquina"]
        id_linea = maquina["id_linea"]
        velocidad_ideal = maquina["velocidad_ideal_ppm"]

        for fecha in fechas:
            for id_turno in turnos_ids:
                try:
                    minutos_parada = tiempo_parada_idx.loc[(id_maquina, fecha, id_turno)]
                except KeyError:
                    minutos_parada = 0.0

                filas = simular_produccion_turno(
                    rng, id_maquina, id_linea, velocidad_ideal,
                    fecha, id_turno, minutos_parada,
                )
                todas_las_filas.extend(filas)

    df = pd.DataFrame(todas_las_filas)
    df.insert(0, "id_produccion", range(1, len(df) + 1))
    return df


if __name__ == "__main__":
    from generar_dimensiones import generar_maquinas, generar_causas_parada
    from simular_paradas import generar_paradas

    maquinas_df = generar_maquinas()
    causas_df = generar_causas_parada()
    paradas_df = generar_paradas(maquinas_df, causas_df)

    produccion_df = generar_produccion(maquinas_df, paradas_df)

    print(f"Total de intervalos de producción generados: {len(produccion_df):,}")
    print("\nMuestra:")
    print(produccion_df.head(10).to_string(index=False))

    print("\nTotales generales:")
    print(f"  Piezas totales:     {produccion_df['piezas_totales'].sum():,.0f}")
    print(f"  Piezas buenas:      {produccion_df['piezas_buenas'].sum():,.0f}")
    print(f"  Piezas rechazadas:  {produccion_df['piezas_rechazadas'].sum():,.0f}")
    print(f"  Tasa de rechazo global: {produccion_df['piezas_rechazadas'].sum() / produccion_df['piezas_totales'].sum() * 100:.2f}%")
