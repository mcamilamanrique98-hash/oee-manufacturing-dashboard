"""
calcular_oee.py
------------------
Agrega las tablas de hechos (produccion_intervalos, paradas) al nivel de
máquina + fecha + turno, y calcula los 3 factores del OEE por separado:

  Disponibilidad = tiempo_operando / tiempo_planeado
  Rendimiento    = (piezas_totales / tiempo_operando) / velocidad_ideal
  Calidad        = piezas_buenas / piezas_totales
  OEE            = Disponibilidad * Rendimiento * Calidad

Nota importante: los 3 factores se calculan de forma INDEPENDIENTE.
Disponibilidad depende del tiempo perdido en paradas.
Rendimiento depende de qué tan rápido produjo la máquina mientras operaba.
Calidad depende de la tasa de rechazo, sin relación con el tiempo.

Salida: una fila por (id_maquina, fecha, id_turno) con todas las métricas.
Esta es la tabla que finalmente se carga a PostgreSQL para el dashboard.
"""

import pandas as pd

import config


def _agregar_produccion(produccion_df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega los intervalos de producción a nivel turno-máquina.
    tiempo_operando se calcula como la suma de la duración de cada intervalo
    (minuto_fin - minuto_inicio), que es distinto de "480 - paradas" porque
    así queda ligado directamente a los datos simulados, no a una fórmula aparte.
    """
    df = produccion_df.copy()
    df["duracion_intervalo"] = df["minuto_fin"] - df["minuto_inicio"]

    agg = (
        df.groupby(["id_maquina", "fecha", "id_turno"])
        .agg(
            piezas_totales=("piezas_totales", "sum"),
            piezas_buenas=("piezas_buenas", "sum"),
            piezas_rechazadas=("piezas_rechazadas", "sum"),
            tiempo_operando_min=("duracion_intervalo", "sum"),
        )
        .reset_index()
    )
    return agg


def _agregar_paradas(paradas_df: pd.DataFrame) -> pd.DataFrame:
    """Agrega la duración total de paradas a nivel turno-máquina."""
    agg = (
        paradas_df.groupby(["id_maquina", "fecha", "id_turno"])["duracion_min"]
        .sum()
        .reset_index()
        .rename(columns={"duracion_min": "tiempo_parada_min"})
    )
    return agg


def calcular_oee(
    produccion_df: pd.DataFrame,
    paradas_df: pd.DataFrame,
    maquinas_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Junta producción + paradas + velocidad ideal de cada máquina,
    y calcula Disponibilidad, Rendimiento, Calidad y OEE.
    """
    prod_agg = _agregar_produccion(produccion_df)
    paradas_agg = _agregar_paradas(paradas_df)

    # Left join: no todos los turnos tienen paradas, por eso left (no inner)
    df = prod_agg.merge(paradas_agg, on=["id_maquina", "fecha", "id_turno"], how="left")
    df["tiempo_parada_min"] = df["tiempo_parada_min"].fillna(0.0)

    # tiempo_planeado: por ahora constante (480 min), ya que no modelamos
    # feriados ni mantenimientos que reduzcan el tiempo planeado del turno
    df["tiempo_planeado_min"] = config.DURACION_TURNO_MIN

    # velocidad_ideal por máquina
    df = df.merge(
        maquinas_df[["id_maquina", "id_linea", "velocidad_ideal_ppm"]],
        on="id_maquina", how="left",
    )

    # --- Los 3 factores del OEE, independientes entre sí ---
    df["disponibilidad"] = df["tiempo_operando_min"] / df["tiempo_planeado_min"]

    # evitar división por cero cuando tiempo_operando_min = 0 (turno totalmente parado)
    df["rendimiento"] = np_divide_seguro(
        df["piezas_totales"] / df["tiempo_operando_min"].replace(0, pd.NA),
        df["velocidad_ideal_ppm"],
    )

    df["calidad"] = np_divide_seguro(df["piezas_buenas"], df["piezas_totales"])

    df["disponibilidad"] = df["disponibilidad"].clip(0, 1)
    df["rendimiento"] = df["rendimiento"].clip(0, 1.2)  # tolerancia leve por ruido positivo
    df["calidad"] = df["calidad"].clip(0, 1)

    df["oee"] = df["disponibilidad"] * df["rendimiento"] * df["calidad"]

    # rellenar turnos totalmente parados (sin producción) con métricas en 0
    df[["rendimiento", "calidad", "oee"]] = df[["rendimiento", "calidad", "oee"]].fillna(0.0)

    columnas_finales = [
        "id_maquina", "id_linea", "fecha", "id_turno",
        "tiempo_planeado_min", "tiempo_operando_min", "tiempo_parada_min",
        "piezas_totales", "piezas_buenas", "piezas_rechazadas",
        "disponibilidad", "rendimiento", "calidad", "oee",
    ]
    return df[columnas_finales].sort_values(["fecha", "id_turno", "id_maquina"]).reset_index(drop=True)


def np_divide_seguro(numerador, denominador):
    """División segura que devuelve NaN en vez de error cuando el denominador es 0/NA."""
    resultado = numerador / denominador
    return resultado


if __name__ == "__main__":
    from generar_dimensiones import generar_maquinas, generar_causas_parada
    from simular_paradas import generar_paradas
    from simular_produccion import generar_produccion

    maquinas_df = generar_maquinas()
    causas_df = generar_causas_parada()
    paradas_df = generar_paradas(maquinas_df, causas_df)
    produccion_df = generar_produccion(maquinas_df, paradas_df)

    oee_df = calcular_oee(produccion_df, paradas_df, maquinas_df)

    print(f"Total de filas OEE (turno-máquina): {len(oee_df):,}")
    print("\nMuestra:")
    print(oee_df.head(10).to_string(index=False))

    print("\n--- OEE promedio general ---")
    print(f"Disponibilidad: {oee_df['disponibilidad'].mean()*100:.1f}%")
    print(f"Rendimiento:    {oee_df['rendimiento'].mean()*100:.1f}%")
    print(f"Calidad:        {oee_df['calidad'].mean()*100:.1f}%")
    print(f"OEE:            {oee_df['oee'].mean()*100:.1f}%")

    print("\n--- OEE promedio por máquina (para detectar anomalías) ---")
    resumen_maquina = oee_df.groupby("id_maquina")["oee"].mean().sort_values()
    print((resumen_maquina * 100).round(1).to_string())
