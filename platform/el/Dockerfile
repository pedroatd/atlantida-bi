# Imagen de las cargas, del almacén, de la IA, del cierre del ciclo y de la orquestación (dlt +
# dbt + MetricFlow + atlantida-ia + atlantida-accion, con las alertas, el reverse ETL y el
# impacto, + Dagster, y el simulador para make historico). La usan el servicio elt (órdenes únicas:
# make pipeline, make accion…) y los tres servicios de Dagster (código, interfaz y daemon). Contexto de
# construcción: la raíz del repositorio (ver .dockerignore). En ejecución no usa la red salvo el
# LLM que se configure (Ollama o, con LLM_PROVIDER, la API externa): sin paquetes de dbt que
# descargar, sin extensiones de DuckDB y sin telemetría. El modelo clásico de reseñas se entrena
# la primera vez y se guarda en /datos/modelos (volumen ia-modelos).
FROM ghcr.io/astral-sh/uv:0.12.22 AS uv

FROM python:3.12.15-slim-trixie AS construccion
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
# 1) Dependencias de terceros (capa que solo cambia con uv.lock).
COPY pyproject.toml uv.lock ./
COPY platform/definicion/pyproject.toml platform/definicion/README.md platform/definicion/
COPY platform/sources/pyproject.toml platform/sources/README.md platform/sources/
COPY platform/el/pyproject.toml platform/el/README.md platform/el/
# Paquete que se instala con sus dependencias: el de Dagster, que arrastra todos los demás, o, en
# una copia sin orquestación (la edición del alumnado llega por etapas), el de las cargas. El ARG
# del bloque, después, sustituye al primero.
ARG PAQUETE=atlantida-el
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --package "$PAQUETE" --no-editable --no-install-workspace
# 2) Paquetes del proyecto (instalación no editable).
COPY platform/definicion platform/definicion
COPY platform/sources platform/sources
COPY platform/el platform/el
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --package "$PAQUETE" --no-editable

FROM python:3.12.15-slim-trixie
ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 \
    DBT_PROJECT_DIR=/opt/atlantida/dbt DBT_PROFILES_DIR=/opt/atlantida/dbt \
    DBT_MANIFEST_CODIGO=/opt/atlantida/manifest DBT_ESTADO_PROD=/datos/estado/prod \
    LAKEHOUSE_DIR=/datos/lakehouse DAGSTER_HOME=/opt/dagster/home DAGSTER_DISABLE_TELEMETRY=1 \
    DO_NOT_TRACK=1 RUNTIME__DLTHUB_TELEMETRY=false EL_DIR_DLT=/tmp/atlantida-dlt
RUN useradd --uid 10001 --create-home atlantida \
    && mkdir -p /datos/mercado /datos/historia /datos/lakehouse /datos/estado /datos/modelos \
       /opt/atlantida/dbt /opt/atlantida/manifest /opt/dagster/home /opt/dagster/datos \
    && chown -R atlantida /datos /opt/atlantida /opt/dagster
COPY --from=construccion /opt/venv /opt/venv
USER atlantida
WORKDIR /opt/atlantida/dbt
ARG REV=desconocida
LABEL org.opencontainers.image.revision=$REV
