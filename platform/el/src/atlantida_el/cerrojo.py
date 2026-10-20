"""Cerrojo del almacén: una sola ejecución a la vez escribe en el DWH (make el, make dbt,
make pipeline, make historico o una corrida de Dagster). Es un cerrojo consultivo de PostgreSQL
(pg_advisory_lock) en la base del DWH: lo libera el servidor si el proceso muere, y lo ven todos
los roles que se conectan a esa base. La conexión que lo guarda lleva un nombre de aplicación
(application_name) para que quien espera sepa qué ejecución lo tiene."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg

from .errores import ErrorDeCarga, error_de_conexion

CLAVE = 7_402_026


class PipelineEnCurso(ErrorDeCarga):
    """Otra ejecución tiene el cerrojo y no lo ha soltado a tiempo."""


def nombre_por_defecto() -> str:
    """El programa y su orden (p. ej. «atlantida-dbt pipeline»), sin opciones: los argumentos
    podrían llevar datos que no deben verse en pg_stat_activity."""
    partes = [Path(sys.argv[0]).name if sys.argv and sys.argv[0] else "python"]
    for a in sys.argv[1:3]:
        if a.startswith("-"):
            break
        partes.append(a)
    return " ".join(partes)[:63]  # PostgreSQL recorta application_name a 63 bytes


def _quien(c: psycopg.Connection) -> str:
    """Quién guarda el cerrojo, según pg_locks y pg_stat_activity (visibles para todo rol)."""
    fila = c.execute(
        "select a.application_name, a.usename, l.pid, "
        "       extract(epoch from now() - a.backend_start)::int "
        "from pg_locks l left join pg_stat_activity a on a.pid = l.pid "
        "where l.locktype = 'advisory' and l.granted "
        "  and l.database = (select oid from pg_database where datname = current_database()) "
        "  and l.classid = %s::oid and l.objid = %s::oid and l.objsubid = 1 "
        "limit 1",
        (CLAVE >> 32, CLAVE & 0xFFFFFFFF),
    ).fetchone()
    if fila is None:
        return "no se ha podido saber qué ejecución lo tiene (acaba de soltarlo)"
    nombre, usuario, pid, segundos = fila
    detalle = [f"proceso {pid} del servidor"]
    if usuario:
        detalle.insert(0, f"rol {usuario}")
    if segundos is not None:
        detalle.append(f"conectado hace {segundos / 60:.0f} min")
    return f"lo tiene «{nombre or 'sin nombre de aplicación'}» ({', '.join(detalle)})"


@contextmanager
def cerrojo(
    url_dwh: str,
    espera_max: float = 1800.0,
    avisar: Callable[[str], None] = print,
    dormir: Callable[[float], None] = time.sleep,
    intervalo: float = 5.0,
    variable_clave: str = "LOADER_PASSWORD",
    aplicacion: str | None = None,
) -> Iterator[None]:
    """variable_clave: la que se nombra si el DWH rechaza la contraseña (el lakehouse usa
    bi_reader).
    aplicacion: el nombre con el que otros verán quién tiene el cerrojo (por omisión, la orden)."""
    try:
        conexion = psycopg.connect(
            url_dwh,
            autocommit=True,
            connect_timeout=10,
            application_name=aplicacion or nombre_por_defecto(),
        )
    except psycopg.OperationalError as exc:
        raise error_de_conexion("el DWH", exc, variable_clave) from None
    # Al salir del with se cierra la conexión pase lo que pase (también con Ctrl+C): el servidor
    # suelta entonces el cerrojo, que es de sesión; si el proceso muere, igual.
    with conexion as c:
        inicio, avisado = time.monotonic(), False
        while not c.execute("select pg_try_advisory_lock(%s)", (CLAVE,)).fetchone()[0]:
            if time.monotonic() - inicio >= espera_max:
                raise PipelineEnCurso(
                    f"Otra ejecución del pipeline sigue en marcha tras {espera_max / 60:.1f} min; "
                    f"{_quien(c)}. Puede ser make pipeline, make historico, make el, make dbt o "
                    "una corrida de Dagster (http://localhost:3000): espera a que termine y "
                    "vuelve a intentarlo."
                )
            if not avisado:
                avisar(
                    "Otra ejecución está escribiendo en el almacén (make pipeline, make historico "
                    f"o Dagster); {_quien(c)}: esperando a que termine…"
                )
                avisado = True
            dormir(intervalo)
        try:
            yield
        finally:
            # Si la conexión se ha caído, el servidor ya soltó el cerrojo: no se tapa el error
            # original con el de este desbloqueo.
            try:
                c.execute("select pg_advisory_unlock(%s)", (CLAVE,))
            except psycopg.Error:
                pass
