-- =========================================================
-- schema.sql
-- Esquema de base de datos para OEE Manufacturing Dashboard
-- Modelo: esquema estrella (star schema)
--   - Dimensiones: lineas, maquinas, turnos, causas_parada
--   - Hechos:       produccion_intervalos, paradas, oee_turno
-- =========================================================

-- Limpieza (útil en desarrollo, para poder re-correr el script sin errores)
DROP TABLE IF EXISTS takt_jph CASCADE;
DROP TABLE IF EXISTS oee_turno CASCADE;
DROP TABLE IF EXISTS paradas CASCADE;
DROP TABLE IF EXISTS produccion_intervalos CASCADE;
DROP TABLE IF EXISTS maquinas CASCADE;
DROP TABLE IF EXISTS lineas CASCADE;
DROP TABLE IF EXISTS turnos CASCADE;
DROP TABLE IF EXISTS causas_parada CASCADE;


-- =========================
-- DIMENSIONES
-- =========================

CREATE TABLE lineas (
    id_linea    SMALLINT PRIMARY KEY,
    nombre      VARCHAR(100) NOT NULL
);

CREATE TABLE maquinas (
    id_maquina          SMALLINT PRIMARY KEY,
    id_linea            SMALLINT NOT NULL REFERENCES lineas(id_linea),
    nombre              VARCHAR(100) NOT NULL,
    velocidad_ideal_ppm NUMERIC(10, 2) NOT NULL  -- piezas por minuto
);

CREATE TABLE turnos (
    id_turno     SMALLINT PRIMARY KEY,
    nombre       VARCHAR(20) NOT NULL,
    hora_inicio  TIME NOT NULL,
    hora_fin     TIME NOT NULL
);

CREATE TABLE causas_parada (
    id_causa            SMALLINT PRIMARY KEY,
    nombre               VARCHAR(100) NOT NULL,
    categoria            VARCHAR(20) NOT NULL CHECK (categoria IN ('Planeada', 'No planeada')),
    prob_relativa         NUMERIC(4, 2),
    duracion_media_min    NUMERIC(6, 2),
    duracion_sd_min       NUMERIC(6, 2)
);


-- =========================
-- HECHOS (nivel evento / intervalo)
-- =========================

CREATE TABLE produccion_intervalos (
    id_produccion       BIGINT PRIMARY KEY,
    id_maquina          SMALLINT NOT NULL REFERENCES maquinas(id_maquina),
    fecha                DATE NOT NULL,
    id_turno             SMALLINT NOT NULL REFERENCES turnos(id_turno),
    minuto_inicio         NUMERIC(6, 1) NOT NULL,
    minuto_fin            NUMERIC(6, 1) NOT NULL,
    piezas_totales        NUMERIC(10, 2) NOT NULL,
    piezas_buenas         NUMERIC(10, 2) NOT NULL,
    piezas_rechazadas     NUMERIC(10, 2) NOT NULL
);

CREATE TABLE paradas (
    id_parada     BIGINT PRIMARY KEY,
    id_maquina    SMALLINT NOT NULL REFERENCES maquinas(id_maquina),
    fecha          DATE NOT NULL,
    id_turno       SMALLINT NOT NULL REFERENCES turnos(id_turno),
    id_causa       SMALLINT NOT NULL REFERENCES causas_parada(id_causa),
    minuto_inicio   NUMERIC(6, 1) NOT NULL,
    minuto_fin      NUMERIC(6, 1) NOT NULL,
    duracion_min    NUMERIC(6, 1) NOT NULL
);


-- =========================
-- HECHOS (nivel agregado: turno-máquina)
-- Esta es la tabla que va a alimentar la mayoría de los paneles de Grafana,
-- porque ya viene con OEE calculado y es mucho más liviana que las de arriba.
-- =========================

CREATE TABLE oee_turno (
    id_maquina            SMALLINT NOT NULL REFERENCES maquinas(id_maquina),
    id_linea              SMALLINT NOT NULL REFERENCES lineas(id_linea),
    fecha                  DATE NOT NULL,
    id_turno               SMALLINT NOT NULL REFERENCES turnos(id_turno),
    tiempo_planeado_min     NUMERIC(6, 1) NOT NULL,
    tiempo_operando_min     NUMERIC(6, 1) NOT NULL,
    tiempo_parada_min       NUMERIC(6, 1) NOT NULL,
    piezas_totales          NUMERIC(10, 2) NOT NULL,
    piezas_buenas           NUMERIC(10, 2) NOT NULL,
    piezas_rechazadas       NUMERIC(10, 2) NOT NULL,
    disponibilidad          NUMERIC(5, 4) NOT NULL,
    rendimiento             NUMERIC(5, 4) NOT NULL,
    calidad                 NUMERIC(5, 4) NOT NULL,
    oee                     NUMERIC(5, 4) NOT NULL,
    PRIMARY KEY (id_maquina, fecha, id_turno)
);


-- =========================
-- HECHOS (Takt Time / JPH — Fase B, terminología de Ingeniería Industrial)
-- Una fila por máquina-día, comparando JPH real vs. JPH objetivo (basado
-- en Takt Time), para detectar cuellos de botella en la línea.
-- =========================

CREATE TABLE takt_jph (
    id_maquina            SMALLINT NOT NULL REFERENCES maquinas(id_maquina),
    id_linea              SMALLINT NOT NULL REFERENCES lineas(id_linea),
    fecha                  DATE NOT NULL,
    piezas_buenas_dia       NUMERIC(10, 2) NOT NULL,
    horas_operando_dia      NUMERIC(6, 3) NOT NULL,
    jph_real                NUMERIC(10, 2) NOT NULL,
    jph_objetivo             NUMERIC(10, 2) NOT NULL,
    takt_time_min            NUMERIC(8, 4) NOT NULL,
    brecha_jph               NUMERIC(10, 2) NOT NULL,
    cumple_takt              BOOLEAN NOT NULL,
    PRIMARY KEY (id_maquina, fecha)
);

CREATE INDEX idx_takt_jph_fecha ON takt_jph (fecha);
CREATE INDEX idx_takt_jph_linea ON takt_jph (id_linea);


-- =========================
-- ÍNDICES
-- Grafana va a filtrar constantemente por fecha y por máquina/línea,
-- así que estos son los patrones de consulta más comunes a optimizar.
-- =========================

CREATE INDEX idx_produccion_fecha ON produccion_intervalos (fecha);
CREATE INDEX idx_produccion_maquina ON produccion_intervalos (id_maquina);

CREATE INDEX idx_paradas_fecha ON paradas (fecha);
CREATE INDEX idx_paradas_maquina ON paradas (id_maquina);
CREATE INDEX idx_paradas_causa ON paradas (id_causa);

CREATE INDEX idx_oee_fecha ON oee_turno (fecha);
CREATE INDEX idx_oee_linea ON oee_turno (id_linea);
