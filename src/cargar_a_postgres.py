"""
cargar_a_postgres.py
------------------------
Orquesta todo el pipeline y carga los DataFrames resultantes a PostgreSQL:

  1. Generar dimensiones (lineas, maquinas, turnos, causas_parada)
  2. Simular paradas
  3. Simular producción
  4. Calcular OEE
  5. Cargar TODO a las tablas ya creadas por schema.sql

Requiere: pip install sqlalchemy psycopg2-binary
"""

import sys

from sqlalchemy import create_engine

import config
from generar_dimensiones import generar_todas_dimensiones
from simular_paradas import generar_paradas
from simular_produccion import generar_produccion
from calcular_oee import calcular_oee


def construir_engine():
    """
    Crea la conexión a PostgreSQL usando SQLAlchemy.
    La contraseña se pide de forma interactiva para no dejarla escrita
    en ningún archivo del repositorio (buena práctica de seguridad).
    """
    import getpass

    password = getpass.getpass("Contraseña de PostgreSQL (usuario postgres): ")

    url = (
        f"postgresql+psycopg2://{config.DB_CONFIG['user']}:{password}"
        f"@{config.DB_CONFIG['host']}:{config.DB_CONFIG['port']}"
        f"/{config.DB_CONFIG['database']}"
    )
    engine = create_engine(url)
    return engine


def cargar_tabla(df, nombre_tabla, engine):
    """
    Carga un DataFrame a una tabla ya existente en PostgreSQL.
    if_exists='append' porque las tablas YA fueron creadas por schema.sql
    (con sus tipos de datos, PK y FK correctos) — no queremos que pandas
    intente recrear la tabla con tipos genéricos.
    """
    print(f"  Cargando {nombre_tabla} ({len(df):,} filas)...", end=" ", flush=True)
    df.to_sql(
        nombre_tabla,
        engine,
        if_exists="append",
        index=False,
        method="multi",   # inserta en lotes, mucho más rápido que fila por fila
        chunksize=5000,    # tamaño de cada lote
    )
    print("OK")


def main():
    print("=== 1. Generando dimensiones ===")
    dims = generar_todas_dimensiones()
    lineas_df = dims["lineas"]
    maquinas_df = dims["maquinas"]
    turnos_df = dims["turnos"]
    causas_df = dims["causas_parada"]
    print(f"  lineas: {len(lineas_df)}, maquinas: {len(maquinas_df)}, "
          f"turnos: {len(turnos_df)}, causas_parada: {len(causas_df)}")

    print("\n=== 2. Simulando paradas ===")
    paradas_df = generar_paradas(maquinas_df, causas_df)
    print(f"  {len(paradas_df):,} eventos de parada generados")

    print("\n=== 3. Simulando producción ===")
    produccion_df = generar_produccion(maquinas_df, paradas_df)
    print(f"  {len(produccion_df):,} intervalos de producción generados")

    print("\n=== 4. Calculando OEE ===")
    oee_df = calcular_oee(produccion_df, paradas_df, maquinas_df)
    print(f"  {len(oee_df):,} filas turno-máquina con OEE calculado")

    print("\n=== 5. Conectando a PostgreSQL ===")
    engine = construir_engine()
    try:
        with engine.connect() as conn:
            pass
        print("  Conexión exitosa.")
    except Exception as e:
        print(f"  ERROR al conectar: {e}")
        sys.exit(1)

    print("\n=== 6. Cargando datos a las tablas ===")
    # Orden importante: primero dimensiones (por las foreign keys),
    # luego hechos crudos, y al final la tabla agregada.
    cargar_tabla(lineas_df, "lineas", engine)
    cargar_tabla(maquinas_df, "maquinas", engine)
    cargar_tabla(turnos_df, "turnos", engine)
    cargar_tabla(causas_df, "causas_parada", engine)
    cargar_tabla(produccion_df, "produccion_intervalos", engine)
    cargar_tabla(paradas_df, "paradas", engine)
    cargar_tabla(oee_df, "oee_turno", engine)

    print("\n✅ Carga completa. Todos los datos están en PostgreSQL.")


if __name__ == "__main__":
    main()
