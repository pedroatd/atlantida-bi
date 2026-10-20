#!/usr/bin/env bash
# Añade a .env las claves de .env.example que falten, con su valor de desarrollo, sin tocar las
# que ya tienen valor (una instalación anterior conserva sus contraseñas y su sal). Las
# contraseñas (*_PASSWORD) y claves secretas (*_SECRET_KEY) que .env.example deja vacías se
# generan al azar. No añade DWH_SEUDONIMO_SAL: la genera sal_seudonimo.sh. Nunca muestra valores.
set -euo pipefail
env_="${1:-.env}"
ejemplo="${2:-.env.example}"
# .env guarda la sal y contraseñas: solo su dueño lo lee (ls -l es portable entre Linux y macOS).
# shellcheck disable=SC2012
if [ "$(ls -ld -- "$env_" | cut -c5-10)" != "------" ]; then
  chmod 600 "$env_"
  echo "AVISO: $env_ lo podían leer otros usuarios del equipo; ahora solo tú (permisos 600)."
fi
[ -z "$(tail -c1 "$env_")" ] || printf '\n' >> "$env_"  # si la última línea no termina en \n

aleatoria() {
  local v
  v=$(openssl rand -hex 24 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(24))')
  [ ${#v} -eq 48 ] || { echo "ERROR: no se pudo generar una contraseña (falta openssl y python3)." >&2; exit 1; }
  printf '%s' "$v"
}
# Pone CLAVE=valor en el fichero (sustituye la línea vacía existente o añade una); el valor viaja
# por el entorno de awk, no por la línea de órdenes.
fijar() {
  local temporal
  temporal=$(mktemp)
  CLAVE="$1" VALOR="$2" awk 'BEGIN { c = ENVIRON["CLAVE"] "="; h = 0 }
    index($0, c) == 1 { if (!h) print c ENVIRON["VALOR"]; h = 1; next }
    { print }
    END { if (!h) print c ENVIRON["VALOR"] }' "$env_" > "$temporal"
  cat "$temporal" > "$env_"  # conserva permisos y propietario de .env
  rm -f -- "$temporal"
}

anadidas=()
generadas=()
while IFS= read -r linea || [ -n "$linea" ]; do
  [[ "$linea" =~ ^([A-Z_][A-Z0-9_]*)=(.*)$ ]] || continue
  clave="${BASH_REMATCH[1]}"
  valor="${BASH_REMATCH[2]}"
  [ "$clave" = DWH_SEUDONIMO_SAL ] && continue
  if [[ ( "$clave" == *_PASSWORD || "$clave" == *_SECRET_KEY ) && -z "$valor" ]]; then
    grep -qE "^${clave}=.+" "$env_" && continue
    fijar "$clave" "$(aleatoria)"
    generadas+=("$clave")
    continue
  fi
  grep -q "^${clave}=" "$env_" && continue
  printf '%s\n' "$linea" >> "$env_"
  anadidas+=("$clave")
done < "$ejemplo"
if [ ${#anadidas[@]} -gt 0 ]; then
  echo "Añadidas a $env_ las claves nuevas de esta versión (valores de desarrollo): ${anadidas[*]}"
fi
if [ ${#generadas[@]} -gt 0 ]; then
  echo "Generadas en $env_ contraseñas y claves aleatorias (no se muestran): ${generadas[*]}"
fi
