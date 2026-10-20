-- Esquemas auxiliares de las cargas (EL). dlt hace el merge en <dataset>_staging; Airbyte (perfil
-- full) escribe en raw_pms_airbyte y guarda sus tablas internas en airbyte_internal. Los escribe
-- el rol loader y transformer lee lo que le corresponde. Idempotente (ver scripts/migrar_dwh.sh).
create schema if not exists raw_pms_staging;
create schema if not exists raw_ext_staging;
create schema if not exists raw_pms_airbyte;
create schema if not exists airbyte_internal;
grant usage, create on schema raw_pms_staging, raw_ext_staging, raw_pms_airbyte, airbyte_internal
  to loader;
grant usage on schema raw_pms_airbyte to transformer;
alter default privileges for role loader in schema raw_pms_airbyte
  grant select on tables to transformer;
