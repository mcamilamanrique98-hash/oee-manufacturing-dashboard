"""
calcular_takt_jph.py
------------------------
Calcula Takt Time y JPH (Jobs Per Hour) por máquina, y los compara para
detectar cuellos de botella — terminología central de Ingeniería Industrial
y de line balancing (usada explícitamente en el puesto de Tesla).

Conceptos:
  Takt Time = ritmo al que DEBE producirse una pieza para cumplir la demanda.
              No depende de qué tan rápido PUEDE ir la máquina, sino de
              cuánto se NECESITA producir.

  JPH (Jobs Per Hour) = piezas buenas producidas por hora, en la práctica.

  Si JPH_real < JPH_objetivo, la máquina no alcanza el ritmo necesario:
  es un cuello de botella para la línea.

Como no simulamos "pedidos de cliente" reales, la demanda objetivo se
define como un % (FACTOR_UTILIZACION_OBJETIVO) de la capacidad teórica
máxima de cada máquina — un enfoque común cuando no hay datos de demanda
real disponibles.
"""

import pandas as pd

import config


def calcular_takt_jph_objetivo(maquinas_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula, para cada máquina, su Takt Time y JPH objetivo — valores fijos
    que dependen solo de su velocidad ideal y el factor de utilización.
    """
    df = maquinas_df.copy()

    # Capacidad teórica: cuántas piezas podría hacer en un día si nunca parara
    df["capacidad_teorica_diaria"] = (
        df["velocidad_ideal_ppm"] * config.MINUTOS_DISPONIBLES_DIA
    )

    # Demanda objetivo: no apuntamos al 100% de capacidad, sino a un % realista
    df["demanda_objetivo_diaria"] = (
        df["capacidad_teorica_diaria"] * config.FACTOR_UTILIZACION_OBJETIVO
    )

    # Takt Time: minutos disponibles / piezas que se necesitan producir
    df["takt_time_min"] = (
        config.MINUTOS_DISPONIBLES_DIA / df["demanda_objetivo_diaria"]
    )

    # JPH objetivo: piezas por hora que hacen falta para cumplir el takt time
    df["jph_objetivo"] = 60 / df["takt_time_min"]

    return df[["id_maquina", "id_linea", "nombre", "velocidad_ideal_ppm",
               "capacidad_teorica_diaria", "demanda_objetivo_diaria",
               "takt_time_min", "jph_objetivo"]]


def calcular_jph_real(oee_df: pd.DataFrame) -> pd.DataFrame:
    """
    Calcula el JPH real por máquina y fecha, a partir de la tabla ya
    agregada oee_turno (sumando los 3 turnos de cada día).
    """
    agg = (
        oee_df.groupby(["id_maquina", "fecha"])
        .agg(
            piezas_buenas_dia=("piezas_buenas", "sum"),
            tiempo_operando_min_dia=("tiempo_operando_min", "sum"),
        )
        .reset_index()
    )

    # Evitar división por cero en días sin tiempo operando
    agg["horas_operando_dia"] = agg["tiempo_operando_min_dia"] / 60
    agg["jph_real"] = agg["piezas_buenas_dia"] / agg["horas_operando_dia"].replace(0, pd.NA)
    agg["jph_real"] = agg["jph_real"].fillna(0.0)

    return agg


def calcular_takt_jph(oee_df: pd.DataFrame, maquinas_df: pd.DataFrame) -> pd.DataFrame:
    """
    Junta JPH real (por día) con JPH objetivo (fijo por máquina) y calcula
    la brecha entre ambos — la métrica clave para detectar cuellos de botella.
    """
    objetivo_df = calcular_takt_jph_objetivo(maquinas_df)
    real_df = calcular_jph_real(oee_df)

    df = real_df.merge(
        objetivo_df[["id_maquina", "id_linea", "nombre", "takt_time_min", "jph_objetivo"]],
        on="id_maquina", how="left",
    )

    # Brecha: negativo significa que la máquina está por debajo del ritmo necesario
    df["brecha_jph"] = df["jph_real"] - df["jph_objetivo"]
    df["cumple_takt"] = df["brecha_jph"] >= 0

    columnas_finales = [
        "id_maquina", "id_linea", "nombre", "fecha",
        "piezas_buenas_dia", "horas_operando_dia",
        "jph_real", "jph_objetivo", "takt_time_min",
        "brecha_jph", "cumple_takt",
    ]
    return df[columnas_finales].sort_values(["fecha", "id_maquina"]).reset_index(drop=True)


if __name__ == "__main__":
    from generar_dimensiones import generar_maquinas, generar_causas_parada
    from simular_paradas import generar_paradas
    from simular_produccion import generar_produccion
    from calcular_oee import calcular_oee

    maquinas_df = generar_maquinas()
    causas_df = generar_causas_parada()
    paradas_df = generar_paradas(maquinas_df, causas_df)
    produccion_df = generar_produccion(maquinas_df, paradas_df)
    oee_df = calcular_oee(produccion_df, paradas_df, maquinas_df)

    print("=== Takt Time y JPH objetivo por máquina (valores fijos) ===")
    objetivo_df = calcular_takt_jph_objetivo(maquinas_df)
    print(objetivo_df[["nombre", "velocidad_ideal_ppm", "takt_time_min", "jph_objetivo"]]
          .round(2).to_string(index=False))

    print("\n=== Calculando JPH real y comparando contra objetivo ===")
    takt_jph_df = calcular_takt_jph(oee_df, maquinas_df)
    print(f"Total de filas (máquina-día): {len(takt_jph_df):,}")

    print("\n=== % de días que cada máquina CUMPLE su takt time ===")
    cumplimiento = (
        takt_jph_df.groupby("nombre")["cumple_takt"]
        .mean()
        .sort_values()
        * 100
    )
    print(cumplimiento.round(1).to_string())

    print("\n(La máquina con menor % de cumplimiento es tu cuello de botella principal)")
