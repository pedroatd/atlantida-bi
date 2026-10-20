"""Carga en crudo de tu proyecto (laboratorio L3): ficheros (tus datos originales) y una base
operacional (tus datos sintéticos, restaurados en proyecto_origen) a la base nueva «proyecto»,
esquema raw, con dlt. Cada fila lleva _loaded_at y _origen; cada tabla y ejecución deja una fila en
meta.carga, también cuando falla. Completa las funciones marcadas como HUECO según tu contrato
(contrato.yml)."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import dlt
import psycopg
from comprobar_carga import (
    ContratoNoValido,
    FaltaVariable,
    FicheroNoValido,
    contrato_desde_yaml,
    filas_de_ficheros,
    leer_csv,
    url_base,
)
from dlt.pipeline.exceptions import PipelineStepFailed
from psycopg.types.json import Jsonb
from sqlalchemy.exc import InvalidRequestError, SQLAlchemyError
from sqlalchemy.exc import OperationalError as OperationalErrorSQLAlchemy

__all__ = ["filas_de_ficheros", "leer_csv"]  # para tus huecos (vienen de comprobar_carga.py)


class HuecoSinCompletar(RuntimeError):
    def __init__(self, nombre: str, pista: str):
        super().__init__(f"completa «{nombre}» en carga.py: {pista}")


class TablaSinCargar(RuntimeError):
    """Una tabla del contrato que dlt no ha cargado (no tiene recurso en los huecos)."""


def url(base: str = "destino") -> str:
    """URL de la base de destino («proyecto») o de la de origen («proyecto_origen»)."""
    return url_base(base)


def cargar_contrato(ruta: Path) -> dict:
    """El contrato validado (ContratoNoValido si no lo es), como diccionario nombre → tabla."""
    return {t.nombre: t for t in contrato_desde_yaml(ruta).tablas}


def recursos_de_ficheros(contrato, carpeta: Path, instante: datetime) -> list:
    """HUECO. Un recurso de dlt por cada tabla de tu contrato con «fichero»:
    dlt.resource(filas_de_ficheros(carpeta, t, instante), name=t.nombre, primary_key=...,
    write_disposition=...), con la clave y la disposición de tu contrato (t.clave,
    t.disposicion). filas_de_ficheros lee todos los ficheros de la tabla con su separador y
    codificación y añade el linaje: _loaded_at, _origen («fichero:<ruta>») y _fila (la línea).
    Un CSV se relee entero en cada ejecución: si declaras «incremental», dlt.sources.incremental
    sobre esa columna solo deja pasar las filas con un valor mayor o igual que el último cargado.
    Los nombres de columna los normaliza dlt (make columnas los enseña)."""
    raise HuecoSinCompletar(
        "recursos_de_ficheros", "un dlt.resource por fichero, con su clave del contrato"
    )


def recursos_de_origen(contrato, instante: datetime) -> list:
    """HUECO. Las tablas del contrato sin «fichero» vienen de proyecto_origen: sql_database
    (from dlt.sources.sql_database import sql_database; credentials=url("origen"),
    schema=t.esquema_origen, table_names=[...]) da un recurso por tabla, en
    fuente.resources[nombre]. A cada uno, apply_hints le pone la clave (primary_key), la
    disposición (write_disposition) y, si la tabla tiene columna incremental, el cursor
    (incremental=dlt.sources.incremental(columna); si la columna tiene nulos, dlt falla salvo
    que elijas on_cursor_value_missing="include" o "exclude": decídelo y dilo en tu nota).
    add_map(f) aplica f a cada fila: f recibe la fila (un diccionario) y la devuelve con
    _loaded_at e _origen (por ejemplo, "proyecto_origen.public.tabla"); cuidado con una lambda
    dentro de un bucle, que ve la última tabla del bucle, y con fijar la tabla con un argumento
    por omisión (lambda fila, t=tabla: ...): dlt puede pasar un segundo argumento a f y pisarlo.
    Una función que fabrique f para cada tabla evita las dos trampas."""
    raise HuecoSinCompletar(
        "recursos_de_origen", "sql_database con las tablas del contrato y su incremental"
    )


def registrar(
    conn, tabla: str, inicio: datetime, fin: datetime, filas: int, estado: str, detalle: dict
) -> None:
    """Deja en meta.carga la fila de una tabla en esta ejecución (fuente «proyecto»)."""
    conn.execute(
        "insert into meta.carga (fuente, tabla, inicio, fin, filas, estado, detalle) "
        "values ('proyecto', %s, %s, %s, %s, %s, %s)",
        (tabla, inicio, fin, filas, estado, Jsonb(detalle)),
    )


def _raiz(exc: BaseException) -> BaseException:
    """La excepción que originó el fallo, bajo los envoltorios de dlt (PipelineStepFailed,
    ResourceExtractionError…)."""
    vistas = set()
    while id(exc) not in vistas:
        vistas.add(id(exc))
        contexto = None if exc.__suppress_context__ else exc.__context__  # «raise … from None»
        siguiente = getattr(exc, "exception", None) or exc.__cause__ or contexto
        if not isinstance(siguiente, BaseException):
            break
        exc = siguiente
    return exc


def _registrar_error(tablas, inicio: datetime, exc: Exception) -> None:
    """Una fila «error» por tabla; si ni siquiera hay conexión, no deja nada (y no lo oculta)."""
    detalle = {"error": type(_raiz(exc)).__name__}
    if isinstance(exc, PipelineStepFailed):
        detalle["paso"] = exc.step
    try:
        with psycopg.connect(url("destino"), autocommit=True, connect_timeout=10) as c:
            for t in tablas:
                registrar(c, t.nombre, inicio, datetime.now(UTC), 0, "error", detalle)
    except (psycopg.Error, FaltaVariable):
        pass


def _esquemas_de_origen(contrato) -> str:
    if contrato is None:
        return "public"
    return ", ".join(sorted({t.esquema_origen for t in contrato.tablas if not t.fichero}))


def _mensaje(exc: Exception, contrato=None) -> str:
    """Mensaje para la terminal, sin trazas ni la URL (que lleva la contraseña)."""
    raiz = _raiz(exc)
    if isinstance(raiz, InvalidRequestError):  # NoSuchTableError al reflejar una tabla
        return (
            "alguna tabla del contrato sin «fichero» no está en proyecto_origen (esquema "
            f"{_esquemas_de_origen(contrato)}): revisa el nombre o restaura tus datos con "
            "make origen"
        )
    if isinstance(raiz, psycopg.OperationalError | OperationalErrorSQLAlchemy) or (
        type(raiz).__name__ == "OperationalError"  # el de psycopg2, que usa dlt para postgres
    ):
        causa = (
            f"no se pudo conectar con la base ({type(raiz).__name__}): ¿está levantada "
            "(make base) y es la contraseña de .env?"
        )
    elif isinstance(raiz, FicheroNoValido):
        causa = str(raiz)
    elif isinstance(raiz, OSError) and raiz.filename:
        causa = f"{raiz.strerror or type(raiz).__name__}: {raiz.filename}"
    elif isinstance(raiz, psycopg.Error | SQLAlchemyError):  # su texto puede llevar la conexión
        causa = f"error de la base ({type(raiz).__name__})"
    elif isinstance(exc, PipelineStepFailed):
        causa = type(raiz).__name__
    else:
        return str(exc)
    if isinstance(exc, PipelineStepFailed):
        texto = f"la carga de dlt falló en {exc.step}: {causa}"
        if exc.step == "load":
            texto += (
                ". dlt guarda la carga fallida y la reintenta al principio de la siguiente "
                "ejecución: corrige la causa y, si vuelve a fallar igual, descártala con "
                "make descartar"
            )
        return texto
    return causa


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--contrato", type=Path, default=Path("contrato.yml"))
    ap.add_argument("--datos", type=Path, default=Path(os.environ.get("PROYECTO_DATOS", "datos")))
    ap.add_argument(
        "--recargar",
        metavar="TABLA",
        help="borra esa tabla de raw y su estado incremental y la carga desde cero",
    )
    args = ap.parse_args(argv)
    contrato = None
    tablas: tuple = ()
    inicio = datetime.now(UTC)
    try:
        contrato = contrato_desde_yaml(args.contrato)
        tablas = contrato.tablas
        if args.recargar:
            tablas = tuple(t for t in contrato.tablas if t.nombre == args.recargar)
            if not tablas:
                raise ContratoNoValido(f"{args.recargar}: no es una tabla del contrato")
        instante = datetime.now(UTC)
        try:
            recursos = []
            if any(t.fichero for t in contrato.tablas):
                recursos += recursos_de_ficheros(contrato, args.datos, instante)
            if any(not t.fichero for t in contrato.tablas):
                recursos += recursos_de_origen(contrato, instante)
            if args.recargar:
                recursos = [r for r in recursos if r.name == args.recargar]
            pipeline = dlt.pipeline(
                "proyecto",
                destination=dlt.destinations.postgres(url("destino")),
                dataset_name="raw",
                pipelines_dir=os.environ.get("PROYECTO_ESTADO_DLT", ".dlt-estado"),
            )
            inicio = datetime.now(UTC)
            info = pipeline.run(recursos, refresh="drop_resources" if args.recargar else None)
        except (OSError, FicheroNoValido, psycopg.Error, SQLAlchemyError, PipelineStepFailed) as e:
            _registrar_error(tablas, inicio, e)
            raise
        fin = datetime.now(UTC)
        filas = pipeline.last_trace.last_normalize_info.row_counts
        conocidas = pipeline.default_schema.data_table_names()
        sin_cargar = [t.nombre for t in tablas if t.nombre not in conocidas]
        with psycopg.connect(url("destino"), autocommit=True) as c:
            for t in tablas:
                if t.nombre in sin_cargar:
                    registrar(c, t.nombre, inicio, fin, 0, "error", {"error": "TablaSinCargar"})
                    continue
                registrar(
                    c,
                    t.nombre,
                    inicio,
                    fin,
                    filas.get(t.nombre, 0),
                    "ok",
                    {"cargas": len(info.loads_ids), "disposicion": t.disposicion},
                )
        if sin_cargar:
            raise TablaSinCargar(
                f"dlt no ha cargado {', '.join(sin_cargar)}: ¿falta su recurso en los huecos "
                "(con name= el nombre de la tabla)?"
            )
    except (
        HuecoSinCompletar,
        TablaSinCargar,
        ContratoNoValido,
        FicheroNoValido,
        FaltaVariable,
        OSError,
        psycopg.Error,
        SQLAlchemyError,
        PipelineStepFailed,
    ) as exc:
        print(f"ERROR: {_mensaje(exc, contrato)}", file=sys.stderr)
        return 1
    print(f"OK carga del proyecto: {len(tablas)} tablas en proyecto.raw")
    return 0


if __name__ == "__main__":
    sys.exit(main())
