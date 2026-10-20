#!/usr/bin/env bash
# Pone en .env una sal secreta y aleatoria para los seudónimos (DWH_SEUDONIMO_SAL) si falta o
# está vacía. Nunca la muestra. Si ya tiene valor, no lo toca: cambiarla cambia los seudónimos.
set -euo pipefail
fichero="${1:-.env}"
publicas='^DWH_SEUDONIMO_SAL=(sal_de_desarrollo|sal_de_desarrollo_cambiala)$'
if grep -qE "$publicas" "$fichero"; then
  echo "AVISO: DWH_SEUDONIMO_SAL de $fichero tiene el valor de ejemplo público: deja la línea vacía" >&2
  echo "       (DWH_SEUDONIMO_SAL=) y vuelve a ejecutar make para generar una sal secreta." >&2
  exit 0
fi
grep -qE '^DWH_SEUDONIMO_SAL=.+' "$fichero" && exit 0
SAL=$(openssl rand -hex 32 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(32))')
[ ${#SAL} -eq 64 ] || { echo "ERROR: no se pudo generar la sal (falta openssl y python3)." >&2; exit 1; }
export SAL
temporal=$(mktemp)
[ -n "$temporal" ] && [ -f "$temporal" ] || { echo "ERROR: no se pudo crear un fichero temporal." >&2; exit 1; }
trap 'if [ -n "${temporal:-}" ] && [ -f "$temporal" ]; then rm -f -- "$temporal"; fi' EXIT
# awk lee la sal del entorno (no de la línea de órdenes, visible en ps).
awk 'BEGIN { hecho = 0 }
     /^DWH_SEUDONIMO_SAL=/ { print "DWH_SEUDONIMO_SAL=" ENVIRON["SAL"]; hecho = 1; next }
     { print }
     END { if (!hecho) print "DWH_SEUDONIMO_SAL=" ENVIRON["SAL"] }' "$fichero" > "$temporal"
cat "$temporal" > "$fichero"  # conserva permisos y propietario de .env
echo "Generada en $fichero una sal secreta para los seudónimos (DWH_SEUDONIMO_SAL; no se muestra)."
