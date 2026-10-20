# Atajos de la plataforma Atlántida. Ejecuta `make help`.
SHELL := /bin/bash
PROFILE ?= lite
COMPOSE = docker compose --profile $(PROFILE)
# Con todos los perfiles (para parar o borrar también el simulador, la API y Ollama, del perfil ai,
# aunque no se pase PROFILE=ai). Ninguna orden hace `$(TODOS) up` sin nombrar el servicio: activar
# un perfil aquí no arranca sus servicios.
TODOS = $(COMPOSE) --profile lite --profile ai --profile full --profile sim --profile vivo --profile servidor --profile elt --profile roles --profile informes
ELT_RUN = $(TODOS) run --rm -T
# make smoke de la edición del alumnado prueba también la API del profesor (scripts/smoke_alumno.sh);
# la edición completa prueba su simulador local (smoke_h03.sh) y no la usa.
SMOKE_API_PROFESOR := ./scripts/smoke_alumno.sh
# Revisión con la que se construye la imagen (etiqueta org.opencontainers.image.revision).
# -dirty también si hay ficheros nuevos sin añadir en el contexto de las imágenes (git describe no los ve)
export ATLANTIDA_REV := $(shell r=$$(git describe --always --dirty 2>/dev/null || echo desconocida); \
  if [ -n "$$(git status --porcelain --untracked-files=normal -- . ../pyproject.toml ../uv.lock 2>/dev/null | grep '^??')" ] \
  && ! echo "$$r" | grep -q -- '-dirty$$'; then r="$$r-dirty"; fi; echo "$$r")
.DEFAULT_GOAL := help

.env:
	cp .env.example .env
	chmod 600 .env
	@echo "Creado .env a partir de .env.example"
	@./scripts/sal_seudonimo.sh .env

help: ## Muestra esta ayuda
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-13s %s\n",$$1,$$2}'

comprobar-env: .env
	@./scripts/completar_env.sh .env .env.example
	@./scripts/sal_seudonimo.sh .env

# Construye las imágenes atlantida-sim y atlantida-elt si no están al día (scripts/imagen.sh).
imagen: ## Construye las imágenes si han cambiado (FORZAR=1 para reconstruirlas siempre)
	@FORZAR="$(FORZAR)" COMPOSE_TODOS="$(TODOS)" ./scripts/imagen.sh

up: comprobar-env imagen ## Levanta la plataforma (PROFILE=lite|ai|full)
	$(COMPOSE) up -d pms-db dwh
	PROFILE=$(PROFILE) ./scripts/esperar_sanos.sh pms-db dwh
	@$(MAKE) --no-print-directory migrar
	@$(MAKE) --no-print-directory roles-pms
	$(COMPOSE) up -d
	PROFILE=$(PROFILE) ESPERA_MAX_SEGUNDOS=300 ./scripts/esperar_sanos.sh

roles-pms: ## Crea o actualiza los roles de acceso al PMS de esta copia de la plataforma (idempotente; lo hace make up)
	@$(TODOS) --progress quiet run --rm pms-el-rol

migrar: ## Aplica al DWH los esquemas, roles y permisos de esta versión (idempotente; lo hace make up)
	@$(COMPOSE) exec -T dwh bash -s < scripts/migrar_dwh.sh

down: ## Detiene la plataforma conservando los datos (reset los borra)
	$(TODOS) down

reset: ## Borra contenedores Y DATOS (pide confirmación)
	@read -p "Se borrarán todos los datos. ¿Seguro? [s/N] " r; case "$$r" in s|S|sí|Sí|si|Si|y|Y) ;; *) echo "Cancelado."; exit 1;; esac
	$(TODOS) down -v

ps: ## Estado de los servicios
	$(TODOS) ps -a

psql-pms: ## Consola SQL del PMS (OLTP)
	@set -a; [ -f .env ] && . ./.env; set +a; \
	$(COMPOSE) exec pms-db psql -U "$${PMS_USER:-pms}" -d "$${PMS_DB:-pms}"

psql-dwh: ## Consola SQL del DWH (OLAP)
	@set -a; [ -f .env ] && . ./.env; set +a; \
	$(COMPOSE) exec dwh psql -U "$${DWH_USER:-dwh_admin}" -d "$${DWH_DB:-dwh}"

smoke: ## Prueba de humo de los servicios que trae esta copia de la plataforma
	./scripts/smoke_h01.sh
	$(SMOKE_API_PROFESOR)


el: comprobar-env imagen roles-pms ## Carga el PMS y las fuentes externas en el DWH (ORIGEN=pms|api; REINICIAR=1 desde cero; SOLO=pms|externas)
	$(ELT_RUN) $(if $(ORIGEN),-e ORIGEN_PMS=$(ORIGEN),) elt atlantida-el cargar $(if $(REINICIAR),--reiniciar,) $(if $(SOLO),--solo $(SOLO),)

# Laboratorio L3: el tercer cargador (../laboratorio/l03/cargador/) y el comprobador del kit se
# ejecutan en el contenedor elt con ../laboratorio montado de solo lectura. DWH_LOADER_URL no
# lleva la contraseña: la toma libpq de PGPASSWORD.
L3_MONTAJE = -v $(abspath ../laboratorio):/laboratorio:ro
L3_LOADER = export PGPASSWORD="$$LOADER_PASSWORD" DWH_LOADER_URL="postgresql://loader@$$DWH_HOST:$$DWH_PORT_INTERNO/$$DWH_DB";

el-estado: comprobar-env imagen ## Últimas cargas registradas en meta.carga (inicio en UTC, fuente, tabla, estado y filas)
	$(ELT_RUN) elt atlantida-el estado

l3-cargador: comprobar-env imagen ## L3 (opcional): ejecuta el tercer cargador, de la API a raw_lab (REINICIAR=1 vacía antes raw_lab)
	$(ELT_RUN) $(L3_MONTAJE) elt sh -c '$(L3_LOADER) exec python /laboratorio/l03/cargador/cargador.py $(if $(REINICIAR),--reiniciar,)'

l3-comprobar: comprobar-env imagen ## L3 (opcional): ejecuta dos veces el tercer cargador y comprueba su contrato frente a raw_pms
	$(ELT_RUN) $(L3_MONTAJE) elt sh -c '$(L3_LOADER) exec python /laboratorio/l03/kit/comprobar_carga.py --contrato-atlantida --dsn-variable DWH_LOADER_URL --esquema raw_lab --fuente lab3 --origen lab3 --referencia raw_pms --orden "python /laboratorio/l03/cargador/cargador.py"'






fuentes: ## Actualiza las instantáneas de fuentes externas (requiere Internet; AEMET_API_KEY opcional)
	@set -a; [ -f .env ] && . ./.env; set +a; cd .. && uv run atlantida-fuentes actualizar $(if $(FUENTE),--fuente $(FUENTE),)

AIRBYTE_CHART ?= 2.3.0

airbyte-instalar: ## Perfil full: instala abctl (versión fijada) y Airbyte en un Kubernetes local (≥ 16 GB de RAM)
	./el/airbyte/instalar_abctl.sh
	./el/airbyte/.bin/abctl local install --chart-version $(AIRBYTE_CHART) --low-resource-mode
	@echo "Copia a AIRBYTE_CLIENT_ID y AIRBYTE_CLIENT_SECRET de .env lo que muestra: ./el/airbyte/.bin/abctl local credentials"

airbyte-configurar: comprobar-env ## Perfil full: aplica la configuración de Airbyte como código (CDC del PMS al DWH)
	@nodo=$$(docker ps --filter name=airbyte-abctl-control-plane --format '{{.Names}}' | head -1); \
	[ -n "$$nodo" ] || { echo "Airbyte no está instalado (make airbyte-instalar)."; exit 1; }; \
	red=$$(docker inspect atlantida-pms-db-1 --format '{{range $$k, $$v := .NetworkSettings.Networks}}{{$$k}}{{end}}'); \
	docker network connect $$red $$nodo 2>/dev/null || true; \
	pms=$$(docker inspect atlantida-pms-db-1 --format "{{(index .NetworkSettings.Networks \"$$red\").IPAddress}}"); \
	dwh=$$(docker inspect atlantida-dwh-1 --format "{{(index .NetworkSettings.Networks \"$$red\").IPAddress}}"); \
	set -a; . ./.env; set +a; cd .. && AIRBYTE_PMS_HOST=$$pms AIRBYTE_DWH_HOST=$$dwh uv run atlantida-el airbyte aplicar

airbyte-sincronizar: comprobar-env ## Perfil full: lanza una sincronización de Airbyte (del PMS al DWH)
	@red=$$(docker inspect atlantida-pms-db-1 --format '{{range $$k, $$v := .NetworkSettings.Networks}}{{$$k}}{{end}}'); \
	pms=$$(docker inspect atlantida-pms-db-1 --format "{{(index .NetworkSettings.Networks \"$$red\").IPAddress}}"); \
	dwh=$$(docker inspect atlantida-dwh-1 --format "{{(index .NetworkSettings.Networks \"$$red\").IPAddress}}"); \
	set -a; . ./.env; set +a; cd .. && AIRBYTE_PMS_HOST=$$pms AIRBYTE_DWH_HOST=$$dwh uv run atlantida-el airbyte sincronizar

airbyte-quitar-ranura: comprobar-env ## Perfil full: borra la ranura de replicación (si no, el PMS acumula WAL; CONFIG=… la de ese fichero)
	@set -a; . ./.env; $(if $(CONFIG),[ -f $(KIT_L3)/.env ] && . $(KIT_L3)/.env;,) set +a; cd .. && uv run atlantida-el airbyte quitar-ranura $(if $(CONFIG),--config $(abspath $(CONFIG)),)

# Airbyte con otra configuración como código (CONFIG): la parte opcional del L3 carga con CDC la
# base proyecto_origen del kit (../laboratorio/l03/kit/airbyte.yml) en su base proyecto. Las
# direcciones AIRBYTE_ORIGEN_HOST y AIRBYTE_DESTINO_HOST son las de la base del kit en su red.
KIT_L3 = $(abspath ../laboratorio/l03/kit)
CONFIG ?=
airbyte-proyecto: comprobar-env ## Perfil full: aplica CONFIG (por omisión, la del kit del L3: CDC de proyecto_origen a proyecto)
	@nodo=$$(docker ps --filter name=airbyte-abctl-control-plane --format '{{.Names}}' | head -1); \
	[ -n "$$nodo" ] || { echo "Airbyte no está instalado (make airbyte-instalar)."; exit 1; }; \
	base=$$(docker ps --filter label=com.docker.compose.project=l03-proyecto --filter label=com.docker.compose.service=base --format '{{.Names}}' | head -1); \
	[ -n "$$base" ] || { echo "La base del kit del L3 no está levantada (make base en laboratorio/l03/kit)."; exit 1; }; \
	red=$$(docker inspect $$base --format '{{range $$k, $$v := .NetworkSettings.Networks}}{{$$k}}{{end}}'); \
	docker network connect $$red $$nodo 2>/dev/null || true; \
	ip=$$(docker inspect $$base --format "{{(index .NetworkSettings.Networks \"$$red\").IPAddress}}"); \
	set -a; . ./.env; [ -f $(KIT_L3)/.env ] && . $(KIT_L3)/.env; set +a; cd .. && AIRBYTE_ORIGEN_HOST=$$ip AIRBYTE_DESTINO_HOST=$$ip uv run atlantida-el airbyte aplicar --config $(abspath $(or $(CONFIG),$(KIT_L3)/airbyte.yml))









.PHONY: help comprobar-env imagen up migrar down reset ps psql-pms psql-dwh smoke roles-pms el
.PHONY: fuentes
.PHONY: el-estado l3-cargador l3-comprobar
.PHONY: airbyte-instalar airbyte-configurar airbyte-sincronizar airbyte-quitar-ranura airbyte-proyecto

# Órdenes de capas que esta copia no tiene (la edición del alumnado llega por etapas): de quién es
# o con qué laboratorio llega. En la edición completa existen todas y esta regla no se usa con
# ellas; con una orden que no existe en ninguna edición, make sigue fallando.
ORDENES_DE_CAPA := seed:profesor reseed:profesor vivo:profesor vivo-parar:profesor servir:profesor \
  servir-parar:profesor historico:profesor servidor-up:profesor servidor-certificado:profesor servidor-parar:profesor \
  servidor-estado:profesor servidor-copia:profesor dbt:L4 pipeline:L4 semantica:L7 docs:L4 lakehouse:L7 \
  orquestar:L5 orquestar-ui:L5 orquestar-activar:L5 orquestar-parar:L5 gobierno:L6 ia:L8 ia-modo:L8 \
  ia-modelo:L8 ia-evaluar:L8 preguntar:L8 superset:L9 informes:L9 informes-parar:L9 alertas:L11 \
  accion:L11 accion-estado:L11 revertir:L11 impacto:L11 airbyte-instalar:L3 airbyte-configurar:L3 \
  airbyte-sincronizar:L3 airbyte-quitar-ranura:L3 airbyte-proyecto:L3 el-estado:L3 l3-cargador:L3 \
  l3-comprobar:L3 openmetadata-instalar:L6 openmetadata-ingestar:L6 \
  openmetadata-quitar:L6
.DEFAULT:
	@d=$$(printf '%s\n' $(ORDENES_DE_CAPA) | sed -n 's/^$@://p'); \
	case "$$d" in \
	  "") echo "make: no hay ninguna orden «$@» (make help)"; exit 2;; \
	  profesor) echo "«make $@» es del profesor: tus datos de Atlántida llegan de su API (ORIGEN_PMS=api; ver platform/el/README.md)."; exit 2;; \
	  *) echo "«make $@» llega con el laboratorio $$d."; exit 2;; \
	esac
