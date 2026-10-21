# Órdenes del kit del laboratorio L3 (carga en crudo de tu proyecto). `make` sin nada las lista.
# .env guarda tu configuración y la contraseña de la base: lo crea la regla de abajo.
include .env
export

COMPOSE = docker compose

.DEFAULT_GOAL := help

help: ## Lista las órdenes del kit
	@grep -E '^[a-z-]+:.*## ' Makefile | awk -F':.*## ' '{printf "  make %-11s %s\n", $$1, $$2}'

# Copia .env.ejemplo a .env (solo lo lee su dueño) y genera la contraseña al azar sin mostrarla.
.env:
	@cp .env.ejemplo .env && chmod 600 .env
	@$(MAKE) --no-print-directory clave-si-falta

clave-si-falta:
	@if ! grep -qE '^PROYECTO_CLAVE=.+' .env; then \
	  v=$$(openssl rand -hex 24 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(24))'); \
	  [ $${#v} -eq 48 ] || { echo "ERROR: no se pudo generar la contraseña (falta openssl y python3)." >&2; exit 1; }; \
	  t=$$(mktemp); \
	  VALOR="$$v" awk 'BEGIN { h = 0 } index($$0, "PROYECTO_CLAVE=") == 1 { if (!h) print "PROYECTO_CLAVE=" ENVIRON["VALOR"]; h = 1; next } { print } END { if (!h) print "PROYECTO_CLAVE=" ENVIRON["VALOR"] }' .env > "$$t"; \
	  cat "$$t" > .env; rm -f -- "$$t"; \
	  echo "Generada en .env una contraseña aleatoria para la base (no se muestra)."; \
	fi

base: ## Levanta tu base nueva (proyecto y proyecto_origen)
	@$(MAKE) --no-print-directory clave-si-falta
	@set -a; . ./.env; set +a; mkdir -p "$${PROYECTO_DATOS:-./datos}"; $(COMPOSE) up -d --wait
	@echo "Base lista en 127.0.0.1:$${PROYECTO_PUERTO:-5440} (bases proyecto y proyecto_origen)."

origen: ## Restaura tus datos SQL en proyecto_origen: make origen F=fichero.sql (o .dump)
	@if [ -z "$(F)" ]; then echo "Uso: make origen F=fichero.sql  (o F=copia.dump de pg_dump -Fc)" >&2; exit 2; fi
	@if [ ! -f "$(F)" ]; then echo "ERROR: no existe $(F)" >&2; exit 2; fi
	@# Todo o nada (una transacción) y sin dueños ni permisos del equipo donde se hizo la copia.
	@case "$(F)" in \
	  *.dump) $(COMPOSE) exec -T base pg_restore --clean --if-exists --no-owner --no-privileges --single-transaction -U "$$PROYECTO_USUARIO" -d proyecto_origen < "$(F)" ;; \
	  *) sed -E '/^ALTER [A-Z ]+ .* OWNER TO /d; /^(GRANT|REVOKE) /d; /^ALTER DEFAULT PRIVILEGES /d' "$(F)" | $(COMPOSE) exec -T base psql -q -X --single-transaction -v ON_ERROR_STOP=1 -U "$$PROYECTO_USUARIO" -d proyecto_origen ;; \
	esac || { echo "ERROR: no se pudo restaurar $(F); no ha quedado nada a medias (se deshace entero). Lee el primer error de arriba." >&2; exit 1; }
	@echo "Restaurado $(F) en proyecto_origen."

contrato: ## Valida contrato.yml y tus ficheros de datos/ sin cargar nada
	uv run --locked python comprobar_carga.py --contrato contrato.yml --solo-contrato

columnas: ## Nombres que dejará dlt para tus cabeceras: make columnas (o F=datos/fichero.csv)
	uv run --locked python comprobar_carga.py --contrato contrato.yml --columnas $(F)

cargar: ## Ejecuta tu carga (carga.py) de datos/ y proyecto_origen a proyecto.raw
	uv run --locked python carga.py

comprobar: ## Carga dos veces y comprueba contrato, idempotencia, registro y origen
	uv run --locked python comprobar_carga.py --contrato contrato.yml --orden "uv run --locked python carga.py"

recargar: ## Borra una tabla de raw y su estado incremental y la carga de cero: make recargar T=tabla
	@if [ -z "$(T)" ]; then echo "Uso: make recargar T=tabla" >&2; exit 2; fi
	uv run --locked python carga.py --recargar "$(T)"

descartar: ## Descarta la carga pendiente que dejó un fallo de dlt (se reintenta en cada ejecución)
	uv run --locked dlt -y pipeline --pipelines-dir "$${PROYECTO_ESTADO_DLT:-.dlt-estado}" proyecto abort-packages

psql: ## Consola SQL: make psql (destino) o make psql BASE=proyecto_origen
	$(COMPOSE) exec base psql -U "$$PROYECTO_USUARIO" -d "$(or $(BASE),proyecto)"

parar: ## Detiene la base conservando los datos
	$(COMPOSE) down

borrar: ## Borra la base Y SUS DATOS y el estado de dlt (pide confirmación; make borrar SI=1 no)
	@if [ "$(SI)" != "1" ]; then read -p "Se borrarán la base del proyecto y sus datos. ¿Seguro? [s/N] " r; case "$$r" in s|S|sí|Sí|si|Si|y|Y) ;; *) echo "Cancelado."; exit 1;; esac; fi
	$(COMPOSE) down -v
	rm -rf .dlt-estado

.PHONY: help clave-si-falta base origen contrato columnas cargar comprobar recargar descartar psql parar borrar
