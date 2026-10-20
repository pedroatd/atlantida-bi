#!/usr/bin/env bash
# Prueba de humo de las bases: bases sanas, esquemas, roles y privilegios correctos.
# Es inocua si se repite: ejecutar `make up` varias veces no daña la plataforma.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; [ -f .env ] && . ./.env; set +a
q() { docker compose exec -T dwh psql -U "${DWH_USER:-dwh_admin}" -d "${DWH_DB:-dwh}" -tAc "$1"; }

esquemas=$(q "select count(*) from information_schema.schemata where schema_name in
  ('raw_pms','raw_ext','staging','snapshots','intermediate','marts_core','marts_revenue',
   'marts_marketing','marts_experiencia','marts_kpi','vault','ml','meta')") || { echo "FALLO: el DWH no responde (¿has ejecutado make up?)"; exit 1; }
[ "$esquemas" = "13" ] || { echo "FALLO: esperados 13 esquemas, hay $esquemas"; exit 1; }

roles=$(q "select count(*) from pg_roles where rolname in ('loader','transformer','ml_writer','bi_reader')") || { echo "FALLO: el DWH no responde (¿has ejecutado make up?)"; exit 1; }
[ "$roles" = "4" ] || { echo "FALLO: esperados 4 roles, hay $roles"; exit 1; }

q "select 1 from meta.carga limit 1" >/dev/null || { echo "FALLO: falta meta.carga o el DWH no responde"; exit 1; }
docker compose exec -T pms-db pg_isready -U "${PMS_USER:-pms}" >/dev/null || { echo "FALLO: PMS no responde (¿has ejecutado make up?)"; exit 1; }
priv() { # priv <esperado t|f> <consulta> <descripción>
  local r; r=$(q "$2") || { echo "FALLO: el DWH no responde"; exit 1; }
  [ "$r" = "$1" ] || { echo "FALLO de privilegios: $3 (esperado $1, obtenido $r)"; exit 1; }
}
priv f "select has_schema_privilege('bi_reader','raw_pms','USAGE')" "bi_reader no debe usar raw_pms"
priv t "select has_schema_privilege('bi_reader','marts_core','USAGE')" "bi_reader debe usar marts_core"
priv t "select has_schema_privilege('transformer','raw_pms','USAGE')" "transformer debe usar raw_pms"
priv f "select has_schema_privilege('loader','staging','USAGE')" "loader no debe usar staging"
echo "OK prueba de humo: bases"
