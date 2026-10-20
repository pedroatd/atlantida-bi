#!/usr/bin/env bash
# Construye las imágenes de la plataforma (atlantida-sim, atlantida-elt, atlantida-superset y
# atlantida-dash, las que tenga esta copia) salvo que ya estén construidas desde esta misma
# revisión del repositorio (etiqueta org.opencontainers.image.revision) y el árbol no tenga cambios
# sin confirmar. FORZAR=1 reconstruye siempre. Si la construcción falla y ya existen, avisa y
# sigue con las construidas; en CI (variable CI) falla.
# Variables (las fija make): ATLANTIDA_REV (git describe --always --dirty) y COMPOSE_TODOS (la
# orden docker compose con todos los perfiles). IMAGEN_SIM, IMAGEN_ELT, IMAGEN_SUPERSET e
# IMAGEN_DASH cambian las etiquetas: como en compose, las del entorno mandan y si no se leen de
# .env (ENV_FILE; make no las exporta). IMAGEN_SOLO (del entorno o de .env): solo esos servicios,
# separados por espacios (p. ej. el servidor del profesor solo usa la del simulador).
set -euo pipefail
cd "$(dirname "$0")/.."
rev="${ATLANTIDA_REV:-desconocida}"
compose="${COMPOSE_TODOS:-docker compose}"
env_="${ENV_FILE:-.env}"
# Solo la línea de esa clave (nunca otras ni la sal); la última, como compose.
de_env() { [ -f "$env_" ] && sed -n "s/^$1=//p" "$env_" | tail -n1 || true; }
sim="${IMAGEN_SIM:-$(de_env IMAGEN_SIM)}"
elt="${IMAGEN_ELT:-$(de_env IMAGEN_ELT)}"
sup="${IMAGEN_SUPERSET:-$(de_env IMAGEN_SUPERSET)}"
das="${IMAGEN_DASH:-$(de_env IMAGEN_DASH)}"
solo="${IMAGEN_SOLO:-$(de_env IMAGEN_SOLO)}"
# Solo las imágenes de los servicios que tiene esta copia (la edición del alumnado llega por
# etapas: en las primeras no hay simulador, Superset ni Dash). La edición completa tiene los cuatro.
# shellcheck disable=SC2086
servicios=$($compose config --services)
construir=()
imagenes=()
for par in "simulator=${sim:-atlantida-sim:0.1.0}" "elt=${elt:-atlantida-elt:0.4.0}" \
  "superset=${sup:-atlantida-superset:0.1.0}" "dash=${das:-atlantida-dash:0.1.0}"; do
  if [ -n "$solo" ] && [[ " $solo " != *" ${par%%=*} "* ]]; then continue; fi
  if printf '%s\n' "$servicios" | grep -qxF -- "${par%%=*}"; then
    construir+=("${par%%=*}")
    imagenes+=("${par#*=}")
  fi
done
if [ ${#construir[@]} -eq 0 ]; then
  echo "Esta copia no tiene imágenes propias que construir."
  exit 0
fi
revision() {
  docker image inspect "$1" --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}' 2>/dev/null
}
if [ "${FORZAR:-0}" != 1 ] && [ "$rev" != desconocida ] && [[ "$rev" != *-dirty ]]; then
  al_dia=1
  for i in "${imagenes[@]}"; do [ "$(revision "$i" || true)" = "$rev" ] || al_dia=0; done
  if [ "$al_dia" = 1 ]; then
    echo "Imágenes al día (revisión $rev): no se reconstruyen (make imagen FORZAR=1 para reconstruirlas)."
    exit 0
  fi
fi
# $compose son varias palabras a propósito.
# Construcción sin la salida de BuildKit; cada IMAGEN_LATIDO segundos (30) dice que sigue.
construir_en_silencio() {
  local latido="${IMAGEN_LATIDO:-30}" t=0 pid estado
  [[ "$latido" =~ ^[1-9][0-9]*$ ]] || latido=30
  # shellcheck disable=SC2086
  $compose --progress quiet build "${construir[@]}" &
  pid=$!
  # Ctrl-C o TERM paran también la construcción en segundo plano (no queda huérfana).
  trap 'kill "$pid" 2>/dev/null; wait "$pid" 2>/dev/null; exit 130' INT TERM
  while kill -0 "$pid" 2>/dev/null; do
    sleep 1
    t=$((t + 1))
    if [ $((t % latido)) -eq 0 ] && kill -0 "$pid" 2>/dev/null; then
      echo "  construyendo… (${t} s)"
    fi
  done
  estado=0
  wait "$pid" || estado=$?
  trap - INT TERM
  return "$estado"
}
if [ "${FORZAR:-0}" != 1 ] && [[ "$rev" == *-dirty ]]; then
  # Con cambios sin confirmar, cada orden de make reconstruye, pero casi todo sale de la caché:
  # una línea en vez de la salida de BuildKit. Si falla, se repite con la salida normal.
  echo "Hay cambios sin confirmar en el repositorio: se ponen al día las imágenes (casi todo sale de la caché; puede tardar minutos si cambiaste código de una imagen)."
  if construir_en_silencio; then exit 0; fi
fi
# shellcheck disable=SC2086
if $compose build "${construir[@]}"; then exit 0; fi
if [ -n "${CI:-}" ]; then
  echo "ERROR: no se pudieron construir las imágenes (en CI no se usa una anterior)." >&2
  exit 1
fi
for i in "${imagenes[@]}"; do
  r=$(revision "$i") || { echo "ERROR: no se pudo construir $i y no hay una anterior." >&2; exit 1; }
  echo "AVISO: no se pudo reconstruir $i; se usa la ya construida (revisión ${r:-desconocida}; repositorio $rev)." >&2
done
