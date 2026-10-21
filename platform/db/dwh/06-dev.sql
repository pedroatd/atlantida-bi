-- Entorno de desarrollo de dbt (destino dev, capítulo 16): las mismas capas con prefijo dev_.
-- Las escribe transformer; ningún rol de consumo (bi_reader, ml_writer) las ve: un cambio a
-- medio probar no llega a los paneles. Las capas raw son comunes (dev lee los mismos datos).
create schema if not exists dev_staging;
create schema if not exists dev_snapshots;
create schema if not exists dev_intermediate;
create schema if not exists dev_marts_core;
create schema if not exists dev_marts_revenue;
create schema if not exists dev_marts_marketing;
create schema if not exists dev_marts_experiencia;
create schema if not exists dev_marts_kpi;
create schema if not exists dev_vault;
grant usage, create on schema dev_staging, dev_snapshots, dev_intermediate, dev_marts_core,
  dev_marts_revenue, dev_marts_marketing, dev_marts_experiencia, dev_marts_kpi, dev_vault
  to transformer;
