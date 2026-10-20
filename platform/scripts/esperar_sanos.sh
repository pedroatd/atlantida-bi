#!/usr/bin/env bash
# Espera a que todos los servicios estén running con health OK (máx. 120 s).
# Tratamiento: servicio running con Health "healthy" está OK; servicio running sin Health (vacío) está OK.
# Solo cuentan los servicios del perfil: la siembra (perfil sim) termina y queda "exited" a propósito.
set -euo pipefail
cd "$(dirname "$0")/.."
max_segundos="${ESPERA_MAX_SEGUNDOS:-120}"
max_iteraciones=$((max_segundos / 2))
if [ $# -gt 0 ]; then
  servicios=$(printf '%s\n' "$@")  # solo estos (make up espera primero a las bases)
else
  servicios=$(docker compose --profile "${PROFILE:-lite}" config --services)
fi
for _ in $(seq 1 $max_iteraciones); do
  output=$(docker compose --profile "${PROFILE:-lite}" ps -a --format '{{.Service}} {{.State}} {{.Health}}' 2>/dev/null \
    | awk -v lista="$servicios" 'BEGIN{n=split(lista,s,"\n"); for(i=1;i<=n;i++) ok[s[i]]=1} ok[$1]{print $2, $3}' || true)
  [ -z "$output" ] && { sleep 2; continue; }
  total=$(echo "$output" | wc -l)
  pending=$(echo "$output" | grep -cv '^\(running healthy\|running \)$' || true)
  [ "$total" -gt 0 ] && [ "$pending" = "0" ] && { echo "Servicios sanos."; exit 0; }
  sleep 2
done
docker compose --profile "${PROFILE:-lite}" ps; echo "Servicios no sanos tras ${max_segundos} s"; exit 1
