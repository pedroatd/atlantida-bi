#!/usr/bin/env bash
# Vuelve a aplicar los guiones de inicialización del DWH (todos son idempotentes): un volumen
# creado con una versión anterior de la plataforma recibe así los esquemas, roles y permisos
# nuevos sin perder datos. Dentro del contenedor dwh (make migrar) usa POSTGRES_USER/POSTGRES_DB;
# desde el anfitrión (pruebas), PGHOST, PGPORT, PGUSER, PGPASSWORD y PGDATABASE.
# MIGRAR_DIR: carpeta de los guiones. MIGRAR_HASTA (pruebas): último prefijo a aplicar, p. ej. 02.
set -euo pipefail
export LC_ALL=C  # orden y comparación de nombres por bytes (con en_US.UTF-8, «02-…» > «02~»)
dir="${MIGRAR_DIR:-/docker-entrypoint-initdb.d}"
export POSTGRES_USER="${POSTGRES_USER:-${PGUSER:?Falta PGUSER o POSTGRES_USER}}"
export POSTGRES_DB="${POSTGRES_DB:-${PGDATABASE:?Falta PGDATABASE o POSTGRES_DB}}"
n=0
export PGOPTIONS="${PGOPTIONS:-} -c client_min_messages=warning"  # sin «ya existe, se omite»
for f in "$dir"/*; do
  nombre=$(basename "$f")
  if [ -n "${MIGRAR_HASTA:-}" ] && [[ "$nombre" > "${MIGRAR_HASTA}~" ]]; then continue; fi
  case "$nombre" in
    *.sql) psql -v ON_ERROR_STOP=1 -q -X --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f "$f" ;;
    *.sh) bash "$f" ;;
    *) continue ;;
  esac
  n=$((n + 1))
done
echo "DWH al día ($n guiones aplicados)."
