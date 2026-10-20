#!/usr/bin/env bash
# Prueba de humo de la edición del alumnado: la API del profesor responde (salud y, con tu token,
# las tablas) y tu almacén tiene cargas correctas desde ella. Nunca muestra el token (viaja a curl
# por la entrada estándar, no en la línea de órdenes). ENV_FILE: el .env que se lee (platform/.env).
set -euo pipefail
cd "$(dirname "$0")/.."
env_="${ENV_FILE:-.env}"
case "$env_" in */*) ;; *) env_="./$env_" ;; esac
set -a
# shellcheck disable=SC1090
[ -f "$env_" ] && . "$env_"
set +a
url="${SIM_API_URL:-}"
url="${url%/}"
[ -n "$url" ] || {
  echo "FALLO: falta SIM_API_URL en platform/.env (la URL de la API que te da el profesor, termina en /v1)."
  exit 1
}

[ -n "${SIM_API_TOKEN:-}" ] || {
  echo "FALLO: falta SIM_API_TOKEN en platform/.env (el token que te da el profesor; su servidor lo pide en todas las rutas)."
  exit 1
}

# get <ruta> <fichero de salida>: deja en codigo el código HTTP (000 si no hubo respuesta) y en
# rc_curl el código de salida de curl (dice por qué no la hubo: DNS, conexión, certificado…).
get() {
  rc_curl=0
  codigo=$(printf 'Authorization: Bearer %s\n' "$SIM_API_TOKEN" |
    curl -sS --max-time 20 -o "$2" -w '%{http_code}' -H @- "$url$1" 2>/dev/null) || rc_curl=$?
  codigo=${codigo:-000}
}
# fallo_http <ruta>: el mensaje de un código distinto de 200, con qué revisar en cada caso.
fallo_http() {
  case "$codigo" in
    000)
      case "$rc_curl" in
        6) por="no se resuelve el nombre del servidor (DNS)" ;;
        7) por="el servidor rechaza la conexión" ;;
        28) por="no hay respuesta en 20 s" ;;
        35 | 51 | 53 | 54 | 58 | 59 | 60 | 66 | 77 | 80 | 82 | 83 | 90 | 91) por="falla el certificado o el TLS" ;;
        *) por="no hay conexión (curl $rc_curl)" ;;
      esac
      echo "FALLO: no se puede conectar con $url$1 (HTTP 000: $por): revisa SIM_API_URL, que el nombre resuelva (DNS) y el certificado; si todo está bien, pregunta al profesor."
      ;;
    401 | 403)
      echo "FALLO: el servidor rechaza el token (SIM_API_TOKEN; HTTP $codigo en $1): revisa SIM_API_TOKEN en platform/.env o pide al profesor el token vigente."
      ;;
    502 | 503 | 504)
      echo "FALLO: el servidor del profesor no está disponible (HTTP $codigo en $1): inténtalo en unos minutos o pregunta al profesor."
      ;;
    *)
      echo "FALLO: GET $url$1 responde HTTP $codigo: revisa SIM_API_URL (termina en /v1) o pregunta al profesor."
      ;;
  esac
  exit 1
}
cuerpo=$(mktemp)
trap 'rm -f "$cuerpo"' EXIT

get /salud "$cuerpo"
[ "$codigo" = 200 ] || fallo_http /salud
grep -q '"estado" *: *"ok"' "$cuerpo" || {
  echo "FALLO: la API del profesor responde en $url/salud, pero su PMS aún no está listo: pregunta al profesor."
  exit 1
}

get /tablas "$cuerpo"
[ "$codigo" = 200 ] || fallo_http /tablas

q() { docker compose exec -T dwh psql -U "${DWH_USER:-dwh_admin}" -d "${DWH_DB:-dwh}" -tAc "$1"; }
# Cargas del PMS desde la API: «total|correctas».
cargas=$(q "select count(*) || '|' || count(*) filter (where estado = 'ok') from meta.carga where fuente = 'api'") || {
  echo "FALLO: el DWH no responde (¿has ejecutado make up?)"
  exit 1
}
total="${cargas%%|*}"
correctas="${cargas##*|}"
if [ "${total:-0}" -eq 0 ]; then
  # Antes de construir el cargador del PMS (L3, parte guiada, paso 4) no hay ninguna: no es un fallo.
  echo "AVISO: aún no hay cargas desde la API del profesor (L3, parte guiada, paso 4: completa fuente_api.py y ejecuta make el SOLO=pms REINICIAR=1)."
  echo "OK prueba de humo: API del profesor (sin cargas desde ella todavía)"
  exit 0
fi
[ "${correctas:-0}" -gt 0 ] || {
  echo "FALLO: tu almacén no tiene cargas correctas desde la API del profesor (make el-estado dice cuáles fallaron): corrige la causa y ejecuta make el SOLO=pms REINICIAR=1."
  exit 1
}
echo "OK prueba de humo: API del profesor y cargas desde ella"
