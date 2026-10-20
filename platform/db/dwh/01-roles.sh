#!/usr/bin/env bash
# Roles por responsabilidad (principio de mínimo privilegio). Ver capítulo 16.
# Las contraseñas llegan como variables de psql (:'nombre'), que psql cita de forma segura:
# nunca se interpolan en el texto SQL desde el shell.
set -euo pipefail
for v in LOADER_PASSWORD TRANSFORMER_PASSWORD ML_WRITER_PASSWORD BI_READER_PASSWORD; do
  [ -n "${!v:-}" ] || { echo "Falta $v en el entorno del contenedor dwh" >&2; exit 1; }
done
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v loader_pw="$LOADER_PASSWORD" -v transformer_pw="$TRANSFORMER_PASSWORD" \
  -v ml_writer_pw="$ML_WRITER_PASSWORD" -v bi_reader_pw="$BI_READER_PASSWORD" <<'SQL'
select format('create role %I login password %L', r, p)
from (values ('loader', :'loader_pw'), ('transformer', :'transformer_pw'),
             ('ml_writer', :'ml_writer_pw'), ('bi_reader', :'bi_reader_pw')) as v(r, p)
where not exists (select from pg_roles where rolname = r) \gexec

grant usage, create on schema raw_pms, raw_ext, meta to loader;
grant usage on schema raw_pms, raw_ext, meta to transformer;
grant select on all tables in schema raw_pms, raw_ext to transformer;
alter default privileges for role loader in schema raw_pms, raw_ext grant select on tables to transformer;
grant usage, create on schema staging, snapshots, intermediate, marts_core, marts_revenue,
  marts_marketing, marts_experiencia, marts_kpi, vault to transformer;
grant usage, create on schema ml to ml_writer;
grant usage on schema marts_core, marts_kpi to ml_writer;
grant usage on schema marts_core, marts_revenue, marts_marketing, marts_experiencia, marts_kpi, ml, meta to bi_reader;
-- ml_writer solo usa marts_core y marts_kpi: en los demás marts un SELECT por defecto sería inerte.
alter default privileges for role transformer in schema marts_core, marts_kpi
  grant select on tables to bi_reader, ml_writer;
alter default privileges for role transformer in schema marts_revenue, marts_marketing,
  marts_experiencia grant select on tables to bi_reader;
alter default privileges for role ml_writer in schema ml grant select on tables to bi_reader;
SQL
