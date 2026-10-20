#!/usr/bin/env bash
# Tablas temporales (privilegio TEMP) solo para quien las usa: loader (dlt, al fusionar) y
# transformer (dbt: incrementales y snapshots). PostgreSQL se las da a PUBLIC por defecto en cada
# base; aquí se retiran en el DWH y en la base «postgres». Idempotente (make migrar).
set -euo pipefail
psql -v ON_ERROR_STOP=1 -q -X --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v base="$POSTGRES_DB" <<'SQL'
revoke temporary on database :"base" from public;
grant temporary on database :"base" to loader, transformer;
revoke temporary on database postgres from public;
SQL
