"""Ejecución de dbt desde Python (dbtRunner) con el proyecto y el perfil de este repositorio."""

from __future__ import annotations

import os
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path

from dbt.cli.main import dbtRunner, dbtRunnerResult

from .rutas import PROYECTO, estado_prod


class ErrorDbt(RuntimeError):
    """dbt terminó con error (modelo, prueba con severidad error o conexión)."""


@contextmanager
def entorno_temporal(extra: dict[str, str]) -> Iterator[None]:
    previo = {k: os.environ.get(k) for k in extra}
    os.environ.update(extra)
    try:
        yield
    finally:
        for k, v in previo.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


_entorno = entorno_temporal  # nombre anterior, por compatibilidad


class SeleccionVacia(ErrorDbt):
    """La selección (--select, --exclude…) no encuentra nodos: dbt no hace nada y sale con 0."""


def _sin_nodos(evento) -> str | None:
    """Criterio de selección sin nodos, si el evento de dbt lo indica."""
    if evento.info.name != "NoNodesForSelectionCriteria":
        return None
    return str(getattr(evento.data, "spec_raw", "") or "")


ORDENES_DIFERIBLES = frozenset({"build", "run", "test", "snapshot", "seed"})
ORDENES_QUE_GUARDAN = frozenset({"build", "run", "snapshot", "seed"})
# Las que toman el cerrojo del almacén (atlantida_el.cerrojo): también test, que puede guardar
# fallos, y retry; las que no escriben (ls, parse, compile, docs…) no esperan.
ORDENES_QUE_ESCRIBEN = ORDENES_DIFERIBLES | {"retry"}


def destino(args: Sequence[str], entorno: Mapping[str, str]) -> str:
    lista = list(args)
    for i, a in enumerate(lista):
        if a in ("--target", "-t"):
            if i + 1 >= len(lista):
                raise ErrorDbt(f"{a} necesita un valor (prod o dev).")
            return lista[i + 1]
        if a.startswith("--target="):
            return a.split("=", 1)[1]
    return entorno.get("DBT_TARGET") or "prod"


def argumentos(args: Sequence[str], entorno: Mapping[str, str]) -> list[str]:
    """Los de la orden más el proyecto y el perfil; en dev, --defer al manifest de prod si existe
    (lo no construido en dev se lee de prod: slim CI)."""
    extra: list[str] = []
    if (
        destino(args, entorno) == "dev"
        and args
        and args[0] in ORDENES_DIFERIBLES
        and "--defer" not in args
        and "--state" not in args
        and (estado_prod() / "manifest.json").is_file()
    ):
        extra = ["--defer", "--state", str(estado_prod())]
    return [*args, *extra, "--project-dir", str(PROYECTO), "--profiles-dir", str(PROYECTO)]


def dbt(
    args: list[str], entorno: dict[str, str] | None = None, permitir_fallo: bool = False
) -> dbtRunnerResult:
    vacios: list[str] = []
    from . import sal

    combinado = {**os.environ, **(entorno or {})}
    extra = {"DO_NOT_TRACK": "1", **(entorno or {}), **sal.para_dbt_segun(args, combinado)}
    if (
        destino(args, combinado) == "dev"
        and args
        and args[0] in ORDENES_DIFERIBLES
        and not (estado_prod() / "manifest.json").is_file()
    ):
        print(
            "Aviso: no hay estado de prod (construye prod una vez, o ejecuta atlantida-dbt "
            "estado-prod): dev construye todo lo seleccionado sin leer nada de prod."
        )
    with entorno_temporal(extra):
        resultado = dbtRunner(
            callbacks=[lambda e: (c := _sin_nodos(e)) is not None and vacios.append(c)]
        ).invoke(argumentos(args, combinado))
    if (
        resultado.success
        and args
        and args[0] in ORDENES_QUE_GUARDAN
        and destino(args, combinado) == "prod"
    ):
        from .estado import guardar_estado_prod  # estado importa este módulo

        guardar_estado_prod(Path(combinado.get("DBT_TARGET_PATH") or PROYECTO / "target"))
    if resultado.success and vacios:
        criterios = ", ".join(f"«{c}»" for c in vacios)
        if any("state:modified" in c for c in vacios):
            raise SeleccionVacia(
                "No hay cambios respecto a prod (state:modified no selecciona nada): "
                "nada que construir en dev."
            )
        raise SeleccionVacia(
            f"dbt {' '.join(args)}: la selección {criterios} no selecciona ningún nodo, así que "
            "dbt no ha hecho nada. Revisa el nombre (p. ej. --select marts.kpi, con el punto de "
            'la carpeta; `make dbt ARGS="ls --select …"` lista lo que selecciona).'
        )
    if not (resultado.success or permitir_fallo):
        motivo = resultado.exception or "revisa los mensajes de dbt de arriba"
        raise ErrorDbt(f"dbt {' '.join(args)} ha fallado: {motivo}")
    return resultado
