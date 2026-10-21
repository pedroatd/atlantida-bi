# Órdenes del kit del laboratorio L4 (modelo dimensional de tu proyecto con dbt). `make` sin nada
# las lista. La base es la del kit del L3: su .env (en L3_KIT, por omisión ../l03-kit) da la
# conexión. El .env de este kit solo guarda la sal de los seudónimos: make sal la genera.
L3_KIT ?= ../l03-kit
-include $(L3_KIT)/.env
-include .env
export

DBT ?= uv run --locked dbt
PY ?= uv run --locked python
export DBT_PROFILES_DIR := $(CURDIR)
# La sal va en la conexión (PGOPTIONS, que libpq lee al conectar) y nunca en el SQL; se lee de
# .env al ejecutar, sin mostrarla. dbt borra de sus registros las variables DBT_ENV_SECRET_*.
SAL = $$(sed -n 's/^PROYECTO_SAL=//p' .env | tail -n 1)
CON_SAL = PGOPTIONS="-c proyecto.sal=$(SAL)" DBT_ENV_SECRET_SAL="$(SAL)"

.DEFAULT_GOAL := help

help: ## Lista las órdenes del kit
	@grep -E '^[a-z-]+:.*## ' Makefile | awk -F':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

hay-l3:
	@if [ ! -f "$(L3_KIT)/.env" ]; then \
	  echo "ERROR: no encuentro $(L3_KIT)/.env, el del kit del L3 (la conexión a tu base). Descomprime este kit junto a l03-kit o di dónde está: make $(or $(MAKECMDGOALS),dbt) L3_KIT=ruta/al/l03-kit" >&2; \
	  exit 2; \
	fi

sal-si-falta:
	@touch .env && chmod 600 .env
	@if ! grep -qE '^PROYECTO_SAL=.+' .env; then \
	  v=$$(openssl rand -hex 32 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(32))'); \
	  [ $${#v} -eq 64 ] || { echo "ERROR: no se pudo generar la sal (falta openssl y python3)." >&2; exit 1; }; \
	  if [ -s .env ] && [ -n "$$(tail -c 1 .env)" ]; then echo >> .env; fi; \
	  printf 'PROYECTO_SAL=%s\n' "$$v" >> .env; \
	  echo "Generada en .env la sal de los seudónimos (no se muestra). No la cambies: cambiaría todos los seudónimos."; \
	fi

sal: sal-si-falta ## Genera en .env la sal de los seudónimos (una sola vez; no se muestra)

fuentes: hay-l3 ## Declara raw en models/staging/_fuentes.yml desde tu contrato del L3
	$(PY) fuentes.py --contrato "$(L3_KIT)/contrato.yml"

dbt: hay-l3 sal-si-falta ## Ejecuta dbt con la sal en la conexión: make dbt ARGS="build" (por omisión)
	@[ -f models/staging/_fuentes.yml ] || echo "AVISO: aún no hay models/staging/_fuentes.yml: ejecuta make fuentes para declarar raw." >&2
	$(CON_SAL) $(DBT) $(or $(ARGS),build)

snapshot: hay-l3 sal-si-falta ## Guarda la historia SCD2 (dbt snapshot): después de cada carga del L3
	@grep -qsE '^ *- *name:|\{% *snapshot' snapshots/*.yml snapshots/*.sql || { \
	  echo "ERROR: no hay ningún snapshot: completa snapshots/plantilla.yml (quita los # y pon tu tabla de staging)." >&2; exit 1; }
	$(CON_SAL) $(DBT) snapshot $(ARGS)

comprobar: hay-l3 sal-si-falta ## Comprueba en la base el modelo que declaras en modelo.yml
	$(CON_SAL) $(PY) comprobar_modelo.py --modelo modelo.yml

docs: hay-l3 sal-si-falta ## Genera y sirve la documentación de dbt en http://127.0.0.1:8080 (PUERTO=…)
	$(CON_SAL) $(DBT) docs generate
	$(DBT) docs serve --host 127.0.0.1 --port $(or $(PUERTO),8080) --no-browser

.PHONY: help hay-l3 sal-si-falta sal fuentes dbt snapshot comprobar docs
