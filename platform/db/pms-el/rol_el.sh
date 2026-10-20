#!/bin/sh
# Rol de solo lectura con el que las cargas (dlt) y el sensor de Dagster leen el PMS: principio
# de mínimo privilegio (capítulo 16). Idempotente: lo ejecutan make up, make seed y make reseed
# (servicio pms-el-rol), también sobre un PMS ya sembrado. Variables: PG* (conexión como
# propietario del PMS), PMS_EL_USER y PMS_EL_PASSWORD.
set -eu
if [ -z "${PMS_EL_USER:-}" ]; then
  echo "AVISO: PMS_EL_USER vacío: las cargas leerán el PMS con su propietario (sin rol de solo lectura)."
  exit 0
fi
if [ "$PMS_EL_USER" = "${PGUSER:-}" ]; then
  echo "PMS_EL_USER no puede ser el propietario del PMS ($PGUSER)." >&2
  exit 1
fi
if [ -z "${PMS_EL_PASSWORD:-}" ]; then
  echo "Falta PMS_EL_PASSWORD para el rol $PMS_EL_USER." >&2
  exit 1
fi
# La contraseña se lee del entorno dentro de psql (\getenv): no aparece en la línea de órdenes.
psql -v ON_ERROR_STOP=1 -q -X <<'SQL'
\getenv usuario PMS_EL_USER
\getenv clave PMS_EL_PASSWORD
select format('create role %I login', :'usuario')
  where not exists (select from pg_roles where rolname = :'usuario') \gexec
select format('alter role %I with login nosuperuser nocreatedb nocreaterole noreplication '
              'password %L', :'usuario', :'clave') \gexec
select format('alter role %I set default_transaction_read_only = on', :'usuario') \gexec
select format('alter role %I set statement_timeout = %L', :'usuario', '30min') \gexec
select format('alter role %I set idle_in_transaction_session_timeout = %L', :'usuario', '10min') \gexec
select format('grant connect on database %I to %I', current_database(), :'usuario') \gexec
select format('grant usage on schema public to %I', :'usuario') \gexec
select format('grant select on all tables in schema public to %I', :'usuario') \gexec
select format('alter default privileges in schema public grant select on tables to %I',
              :'usuario') \gexec
-- Del esquema interno del simulador, solo el reloj (el sensor de Dagster y la línea base lo leen).
select format('grant usage on schema sim to %I', :'usuario')
  where to_regnamespace('sim') is not null \gexec
select format('grant select on sim.reloj to %I', :'usuario')
  where to_regclass('sim.reloj') is not null \gexec
SQL
echo "Rol de solo lectura $PMS_EL_USER listo para las cargas (public y sim.reloj)."
