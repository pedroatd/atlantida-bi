"""Manifests de dbt fuera de target/. `dbt parse --target prod` no necesita la base de datos y
fija los nombres de las relaciones de prod (con la DWH_DB del entorno en que se ejecuta)."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path

from .ejecutar import dbt
from .rutas import estado_prod, manifest_codigo


def parsear(destino_dbt: str, carpeta: Path, entorno: Mapping[str, str] | None = None) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    dbt(
        ["parse", "--target", destino_dbt, "--target-path", str(carpeta), "--no-partial-parse"],
        entorno={**(entorno or {}), "DBT_TARGET": destino_dbt},
    )
    return carpeta / "manifest.json"


def generar_manifest_codigo(carpeta: Path | None = None) -> Path:
    destino = carpeta or manifest_codigo()
    with tempfile.TemporaryDirectory(prefix="dbt-codigo-") as t:
        manifest = parsear("prod", Path(t))
        destino.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(manifest, destino / "manifest.json")
    return destino / "manifest.json"


ARTEFACTOS = ("manifest.json", "run_results.json")


def guardar_estado_prod(target: Path, destino: Path | None = None) -> Path | None:
    """Copia el manifest (y los resultados) de una ejecución correcta en prod al estado de prod.
    Cada fichero se escribe aparte y se renombra: quien lo lea nunca ve uno a medias. Es lo que
    compara state:modified en dev: el código editado frente a lo que de verdad se construyó.
    También se guarda tras una construcción parcial (--select): el manifest es el del proyecto
    entero, así que un modelo editado y aún sin construir deja de contar como modificado; para
    una comparación completa, construye prod entero. Es el compromiso asumido."""
    if not (target / "manifest.json").is_file():
        return None
    destino = destino or estado_prod()
    destino.mkdir(parents=True, exist_ok=True)
    for nombre in ARTEFACTOS:
        if (target / nombre).is_file():
            temporal = destino / f".{nombre}.nuevo"
            shutil.copyfile(target / nombre, temporal)
            temporal.replace(destino / nombre)
        else:  # sin resultados nuevos, los viejos no casarían con el manifest nuevo
            (destino / nombre).unlink(missing_ok=True)
    return destino / "manifest.json"


def generar_estado_prod(
    entorno: Mapping[str, str] | None = None,
    destino: Path | None = None,
    forzar: bool = False,
) -> Path | None:
    """Antes de la primera construcción en prod: el estado sale de dbt parse en este entorno (con
    su DWH_DB, para que --defer apunte a la base correcta). Si ya hay un estado (de una
    construcción real) no se toca, salvo con forzar: un parse no sustituye a lo construido."""
    existente = (destino or estado_prod()) / "manifest.json"
    if existente.is_file() and not forzar:
        return existente
    with tempfile.TemporaryDirectory(prefix="dbt-prod-") as t:
        return guardar_estado_prod(parsear("prod", Path(t), entorno).parent, destino)
