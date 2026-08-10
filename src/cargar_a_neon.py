"""
cargar_a_neon.py
------------------
Igual que cargar_a_postgres.py, pero apunta a una base de datos en Neon
(PostgreSQL en la nube) en vez de a PostgreSQL local.

Esto es lo que hace que el dashboard de Grafana Cloud pueda funcionar
24/7 sin depender de que tu computadora esté encendida.

Requiere: pip install sqlalchemy psycopg2-binary
"""

import sys
import getpass

from sqlalchemy import create_engine

from generar_dimensiones import generar_todas_dimensiones
from simular_paradas import generar_paradas
from simular_produccion import generar_produccion
from calcular_oee import calcular_oee
from calcular_takt_jph import calcular_takt_jph


def construir_engine_neon():
    """
    Pide la connection string completa de Neon (la que copiaste del
    dashboard de Neon) y crea la conexión.
    SQLAlchemy espera el prefijo 'postgresql+psycopg2://' en vez de
    'postgresql://', así que lo ajustamos automáticamente si hace falta.
    """
    print("Pega tu connection string de Neon (la que copiaste del dashboard).")
    print("Formato esperado: postgresql://usuario:password@host/dbname?sslmode=require")
    connection_string = getpass.getpass("Connection string (no se mostrará en pantalla): ").strip()

    if connection_string.startswith("postgresql://"):
        connection_string = connection_string.replace(
            "postgresql://", "postgresql+psycopg2://", 1
        )
    elif connection_string.startswith("postgres://"):
        connection_string = connection_string.replace(
            "postgres://", "postgresql+psycopg2://", 1
        )

    engine = create_engine(connection_string)
    return engine


def cargar_tabla(df, nombre_tabla, engine):
    print(f"  Cargando {nombre_tabla} ({len(df):,} filas)...", end=" ", flush=True)
    df.to_sql(
        nombre_tabla,
        engine,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=2000,   # lotes un poco más chicos que en local, por la latencia de red
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

    print("\n=== 4b. Calculando Takt Time / JPH ===")
    takt_jph_df = calcular_takt_jph(oee_df, maquinas_df)
    print(f"  {len(takt_jph_df):,} filas máquina-día con Takt Time/JPH calculado")
    # La tabla SQL no tiene columna 'nombre' (se obtiene vía JOIN con maquinas)
    takt_jph_df = takt_jph_df.drop(columns=["nombre"])

    print("\n=== 5. Conectando a Neon ===")
    engine = construir_engine_neon()
    try:
        with engine.connect() as conn:
            pass
        print("  Conexión exitosa.")
    except Exception as e:
        print(f"  ERROR al conectar: {e}")
        sys.exit(1)

    print("\n=== 6. Cargando datos a las tablas (puede tardar un poco más que en local, por la red) ===")
    cargar_tabla(lineas_df, "lineas", engine)
    cargar_tabla(maquinas_df, "maquinas", engine)
    cargar_tabla(turnos_df, "turnos", engine)
    cargar_tabla(causas_df, "causas_parada", engine)
    cargar_tabla(produccion_df, "produccion_intervalos", engine)
    cargar_tabla(paradas_df, "paradas", engine)
    cargar_tabla(oee_df, "oee_turno", engine)
    cargar_tabla(takt_jph_df, "takt_jph", engine)

    print("\n✅ Carga completa. Los datos ya están en Neon, listos para conectar Grafana Cloud.")


if __name__ == "__main__":
    main()
