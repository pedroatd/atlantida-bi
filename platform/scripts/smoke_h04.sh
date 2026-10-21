#!/usr/bin/env bash
# Prueba de humo del almacén: cargas registradas, capas construidas y objetivos evaluados.
# SMOKE_DWH=1 la exige (CI, tras make pipeline); sin ella, si el almacén está vacío solo avisa.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ -f .env ]; then
  while IFS='=' read -r k v; do
    [[ "$k" =~ ^[A-Z_][A-Z0-9_]*$ ]] && [ -z "${!k+x}" ] && export "$k=$v" || true
  done < .env
fi
q() { docker compose exec -T dwh psql -U "${DWH_USER:-dwh_admin}" -d "${DWH_DB:-dwh}" -tAc "$1"; }
fallo() { echo "FALLO: $1"; exit 1; }

construido=$(q "select to_regclass('marts_kpi.objetivo_logro') is not null") \
  || fallo "el DWH no responde (¿has ejecutado make up?)"
if [ "$construido" != "t" ]; then
  [ "${SMOKE_DWH:-0}" = "1" ] && fallo "el almacén no está construido (ejecuta make pipeline)"
  echo "AVISO: el almacén aún no está construido (make pipeline); no se comprueba."
  exit 0
fi
cargas=$(q "select count(*) from meta.carga where estado in ('ok', 'instantanea')")
[ "$cargas" -gt 0 ] || fallo "meta.carga no registra ninguna carga correcta"
raw=$(q "select count(*) from raw_pms.reservation")
hechos=$(q "select count(*) from marts_core.fct_reserva")
[ "$raw" = "$hechos" ] || fallo "raw_pms.reservation ($raw) y marts_core.fct_reserva ($hechos) no cuadran"
objetivos=$(q "select count(*) from marts_kpi.objetivo_logro where ambito = 'CADENA' and evaluacion = 'anual'")
[ "$objetivos" = "4" ] || fallo "objetivo_logro no tiene los cuatro objetivos de la cadena"
echo "OK prueba de humo: almacén ($hechos reservas, $objetivos objetivos evaluados)"
