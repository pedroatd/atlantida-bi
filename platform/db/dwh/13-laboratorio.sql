-- Esquema del tercer cargador del laboratorio L3 (laboratorio/l03/cargador/, ejercicio opcional):
-- un cargador sin dlt deja aquí las tablas del PMS y su cursor (raw_lab._cursor) y registra sus
-- cargas en meta.carga con fuente = 'lab3'. Es del rol loader, que crea en él sus tablas; nadie
-- más lo lee (dbt sigue leyendo raw_pms). Idempotente (ver scripts/migrar_dwh.sh).
create schema if not exists raw_lab authorization loader;
