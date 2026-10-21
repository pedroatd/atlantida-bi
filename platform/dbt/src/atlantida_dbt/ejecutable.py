"""atlantida-dbt-exec: dbt con las opciones de sesión de Atlántida, para quien lanza dbt como
proceso aparte (Dagster: DbtCliResource(dbt_executable="atlantida-dbt-exec")).

Antes de arrancar dbt, en su propio proceso, añade al entorno la sal de los seudónimos y el límite
de las consultas (PGOPTIONS, ver sal.para_dbt) y fija DBT_TARGET=prod salvo que la orden pida
otro destino con --target. Quien lo lanza no toca su propio entorno: la sal ya está en él como
DWH_SEUDONIMO_SAL y PGOPTIONS solo existe en el proceso de dbt.

`--version` responde aquí con las versiones instaladas: la de dbt consulta PyPI, y dagster-dbt la
pide al empezar cada corrida (la plataforma no usa la red en ejecución)."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence

from atlantida_el.errores import ErrorDeCarga

from . import sal
from .ejecutar import destino


def variables(args: Sequence[str], entorno: Mapping[str, str]) -> dict[str, str]:
    """Lo que se añade al entorno de dbt. Las órdenes que no construyen (--version, ls, parse…)
    funcionan sin sal; build, run, snapshot y retry la exigen (sal.para_dbt_segun)."""
    pide_destino = any(a in ("--target", "-t") or a.startswith("--target=") for a in args)
    return {
        "DO_NOT_TRACK": "1",
        "DBT_TARGET": destino(args, entorno) if pide_destino else "prod",
        **sal.para_dbt_segun(list(args), entorno),
    }


def version_local() -> str:
    """Como `dbt --version` (dagster-dbt busca el primer X.Y.Z), sin comprobar si hay otra más
    nueva en PyPI."""
    from importlib.metadata import version

    return (
        f"Core:\n  - installed: {version('dbt-core')}\n\n"
        f"Plugins:\n  - postgres: {version('dbt-postgres')}\n"
    )


def main(argv: Sequence[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--version"]:
        print(version_local(), end="")
        return
    try:
        extra = variables(args, os.environ)
    except ErrorDeCarga as exc:  # sal no válida o límite mal escrito: el mensaje dice qué hacer
        print(f"atlantida-dbt-exec: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    os.environ.update(extra)  # el entorno de este proceso, que es el de dbt
    from dbt.cli.main import cli

    cli.main(args=args, prog_name="dbt")
