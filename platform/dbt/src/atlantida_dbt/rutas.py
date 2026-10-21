"""Dónde está el proyecto dbt: DBT_PROJECT_DIR (imagen) o platform/dbt (instalación editable)."""

from __future__ import annotations

import os
from pathlib import Path


def _proyecto() -> Path:
    if os.environ.get("DBT_PROJECT_DIR"):
        return Path(os.environ["DBT_PROJECT_DIR"])
    return Path(__file__).resolve().parents[2]


PROYECTO = _proyecto()


def estado_prod() -> Path:
    """Estado de la última construcción correcta en prod (manifest y run_results): lo usa
    --defer/--state en dev. DBT_ESTADO_PROD (volumen dbt-estado en Compose) o
    platform/dbt/estado/prod."""
    return Path(os.environ.get("DBT_ESTADO_PROD") or PROYECTO / "estado" / "prod")


def manifest_codigo() -> Path:
    """Manifest del código (dbt parse con el destino prod): lo leen Dagster (assets, checks y
    linaje) y el diccionario. DBT_MANIFEST_CODIGO (la imagen lo genera al construirse) o
    platform/dbt/estado/codigo."""
    return Path(os.environ.get("DBT_MANIFEST_CODIGO") or PROYECTO / "estado" / "codigo")
