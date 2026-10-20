"""El tercer cargador (laboratorio L3, ejercicio opcional): Atlántida desde la API de cambios del
profesor hasta el DWH, sin dlt, solo con httpx y psycopg.

Es el ejercicio 2, «Sustituir dlt», del capítulo 14 del libro («Herramientas por fase y criterios
de elección»), llevado a código: un motor de carga distinto de dlt que respeta el mismo contrato,
para que dbt pudiera leer lo que deja sin cambiar nada. El contrato que debe cumplir:

- Escribe en el esquema raw_lab del DWH (no en raw_pms, que es de dlt): una tabla por cada tabla de
  GET /v1/tablas, con el mismo nombre y sus columnas (los nombres y tipos de «columnas»), más
  _loaded_at (instante de la carga, timestamptz no nulo) y _origen (el literal 'lab3', no nulo).
- Carga incremental idempotente: upsert por la «clave» de /v1/tablas (insert … on conflict (clave)
  do update), de modo que repetir la carga no duplica filas. Las tablas con «clave_con_nulos» no
  vacía se releen enteras en cada carga (vaciar e insertar): NULL no casa en un upsert. Las demás
  se combinan, también guest_flag, aunque dlt la relee entera en raw_pms para que le lleguen las
  marcas que el reverse ETL borra (lo decide RELEER_ENTERAS, en el esquema.py de platform/el, y
  /v1/tablas no lo publica). Mientras el PMS del profesor no borre marcas, las dos cargas
  coinciden; si borrara una, l3-comprobar diría que sobran filas de guest_flag en raw_lab, y sería
  esta diferencia de contrato, no un fallo de tu cargador.
- Cursor por tabla en raw_lab._cursor(tabla, cursor, hasta): el cursor opaco de la última página
  leída y el «hasta» de esa sincronización. La carga siguiente pide /v1/cambios desde ese cursor;
  sin cursor, desde el principio. El cursor se guarda en la misma transacción que las filas: si la
  carga falla a medias, ni las filas ni el cursor avanzan.
- Paginación: GET /v1/cambios?tabla=…&limite=…[&hasta=…][&cursor=…] devuelve {"filas", "cursor",
  "hay_mas", "hasta"}. El parámetro «hasta» es opcional: con él, la API corta en el menor entre él
  y su reloj; sin él, en su reloj. En los dos casos la respuesta trae en «hasta» el corte que
  aplicó. Este cargador no fija un corte común a todas las tablas (a diferencia de fuente_api.py
  en la plataforma): cada tabla pide su primera página sin «hasta», repite en las siguientes el
  que devolvió la primera y sigue el cursor mientras «hay_mas» sea verdadero.
- Registro: una fila por tabla y ejecución en meta.carga, con fuente = 'lab3', tabla, inicio,
  fin, filas (las leídas en esta ejecución) y estado ('ok' o 'error'; en error, el motivo en
  «detalle»).
- 409 (el profesor ha vuelto a sembrar el PMS): el cursor guardado ya no vale; hay que recargar
  desde cero (vaciar raw_lab y sus cursores): lanza Recargar. 401: el token no vale: lanza
  TokenNoValido con un mensaje que diga que se revise SIM_API_TOKEN. main captura las dos.

Variables de entorno (make l3-cargador las pone): SIM_API_URL (termina en /v1), SIM_API_TOKEN y
DWH_LOADER_URL (la base del DWH con el rol loader). Se ejecuta con `make l3-cargador` y se
comprueba con `make l3-comprobar` (desde platform/). Salida: 0 si todo fue bien, 1 si hubo un
error y 3 si hay que volver a ejecutarla porque se recargó desde cero.

Completa las funciones que lanzan NotImplementedError («completa la función …»); main ya está
escrita y las usa en este orden."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import psycopg

ESQUEMA = "raw_lab"
FUENTE = "lab3"
SALIDA_ERROR, SALIDA_RECARGA = 1, 3


class Recargar(RuntimeError):
    """La API respondió 409: el PMS se ha vuelto a sembrar y hay que recargar desde cero."""


class TokenNoValido(RuntimeError):
    """La API respondió 401: el token no vale (su mensaje dice que se revise SIM_API_TOKEN)."""


def leer_tablas(api: httpx.Client) -> list[dict]:
    """Las tablas que sirve la API (GET /tablas): una entrada por tabla con «tabla», «columnas»
    ([{"nombre", "tipo"}]), «clave» y «clave_con_nulos». Un 401 lanza TokenNoValido, con un
    mensaje que diga que se revise SIM_API_TOKEN."""
    raise NotImplementedError(
        "completa la función leer_tablas: pide /tablas con api.get y devuelve su JSON"
    )


def leer_cambios(api: httpx.Client, tabla: str, cursor: str | None) -> Iterator[dict]:
    """Las páginas de GET /cambios de «tabla» desde «cursor» (None: desde el principio), cada
    una como su cuerpo JSON ({"filas", "cursor", "hay_mas", "hasta"}). La primera va sin
    «hasta» (la API corta en su reloj); las siguientes repiten el que devolvió la primera. Para
    cuando «hay_mas» es falso.
    Un 409 lanza Recargar y un 401, TokenNoValido."""
    raise NotImplementedError(
        "completa la función leer_cambios: pide /cambios con params tabla, limite y cursor, "
        "repite el «hasta» de la primera respuesta y sigue el cursor mientras hay_mas"
    )


def asegurar_tabla(conn: psycopg.Connection, tabla: dict, vaciar: bool = False) -> None:
    """Crea raw_lab.<tabla> si no existe: las columnas de «columnas» con su tipo, _loaded_at
    timestamptz not null y _origen text not null y, si la clave no admite nulos, una restricción
    única (o clave primaria) sobre la «clave», que es la que usa el upsert. Con vaciar, deja la
    tabla vacía (relectura entera o recarga desde cero). Usa psycopg.sql para los nombres."""
    raise NotImplementedError(
        "completa la función asegurar_tabla: create table if not exists con sql.Identifier y, "
        "con vaciar, truncate"
    )


def escribir(conn: psycopg.Connection, tabla: dict, filas: list[dict], instante: datetime) -> int:
    """Escribe «filas» en raw_lab.<tabla> con _loaded_at = instante y _origen = 'lab3': upsert
    por la clave (insert … on conflict (clave) do update set …) o, si la tabla se relee entera,
    insert. Devuelve el número de filas escritas (el registro de meta.carga no lo usa: anota las
    leídas, que cuenta _cargar_tabla)."""
    raise NotImplementedError(
        "completa la función escribir: insert … on conflict (clave) do update con "
        "conn.cursor().executemany"
    )


def registrar(
    conn: psycopg.Connection,
    tabla: str,
    inicio: datetime,
    filas: int | None,
    estado: str,
    detalle: dict | None = None,
) -> None:
    """Anota en meta.carga una fila de esta ejecución para «tabla»: fuente 'lab3', inicio, fin
    (ahora), filas, estado ('ok' o 'error') y detalle (jsonb; en error, el motivo)."""
    raise NotImplementedError(
        "completa la función registrar: insert into meta.carga (fuente, tabla, inicio, fin, "
        "filas, estado, detalle)"
    )


def guardar_cursor(
    conn: psycopg.Connection, tabla: str, cursor: str | None, hasta: str | None
) -> None:
    """Guarda (upsert por tabla) el cursor y el «hasta» de «tabla» en raw_lab._cursor; con
    cursor None, la tabla vuelve a leerse desde el principio."""
    raise NotImplementedError(
        "completa la función guardar_cursor: insert into raw_lab._cursor … on conflict (tabla) "
        "do update"
    )


def leer_cursor(conn: psycopg.Connection, tabla: str) -> str | None:
    """El cursor guardado de «tabla» en raw_lab._cursor, o None si no hay. Crea antes
    raw_lab._cursor si no existe (tabla text primary key, cursor text, hasta text)."""
    raise NotImplementedError(
        "completa la función leer_cursor: create table if not exists raw_lab._cursor y select "
        "del cursor de la tabla"
    )


def _cliente_api() -> httpx.Client:
    token = os.environ.get("SIM_API_TOKEN", "")
    return httpx.Client(
        base_url=os.environ["SIM_API_URL"].rstrip("/"),
        headers={"Authorization": f"Bearer {token}"} if token else {},
        timeout=60,
    )


def _cargar_tabla(api: httpx.Client, conn: psycopg.Connection, t: dict, instante) -> int:
    """Una tabla en una transacción: sus filas, su cursor y su registro avanzan juntos. El
    registro anota las filas leídas de la API (las que trae cada página), no las que escribir dice
    que cambió: un upsert que no actualiza no puede esconderse tras su recuento."""
    releer = bool(t["clave_con_nulos"])
    inicio = datetime.now(UTC)
    with conn.transaction():
        asegurar_tabla(conn, t, vaciar=releer)
        cursor = None if releer else leer_cursor(conn, t["tabla"])
        leidas, hasta = 0, None
        for pagina in leer_cambios(api, t["tabla"], cursor):
            filas = pagina.get("filas") or []
            escribir(conn, t, filas, instante)
            leidas += len(filas)
            cursor, hasta = pagina.get("cursor") or cursor, pagina.get("hasta") or hasta
        guardar_cursor(conn, t["tabla"], None if releer else cursor, hasta)
        registrar(conn, t["tabla"], inicio, leidas, "ok")
    return leidas


def _recargar(conn: psycopg.Connection, tablas: list[dict]) -> None:
    with conn.transaction():
        for t in tablas:
            asegurar_tabla(conn, t, vaciar=True)
            leer_cursor(conn, t["tabla"])
            guardar_cursor(conn, t["tabla"], None, None)


def main(argv: list[str] | None = None) -> int:
    """Carga cada tabla de la API en raw_lab y la registra en meta.carga; con --reiniciar, vacía
    antes raw_lab y sus cursores. Un 409 recarga desde cero en la ejecución siguiente (sale con
    3); un hueco sin completar o un error salen con 1, con un mensaje y sin traza."""
    ap = argparse.ArgumentParser(description="Tercer cargador del L3: API de cambios → raw_lab.")
    ap.add_argument("--reiniciar", action="store_true", help="vacía raw_lab y sus cursores antes")
    args = ap.parse_args(argv)
    faltan = [v for v in ("SIM_API_URL", "DWH_LOADER_URL") if not os.environ.get(v)]
    if faltan:
        print(f"ERROR: falta {', '.join(faltan)} (make l3-cargador las pone)", file=sys.stderr)
        return SALIDA_ERROR
    instante = datetime.now(UTC)
    errores = 0
    try:
        with _cliente_api() as api:
            tablas = leer_tablas(api)
            with psycopg.connect(os.environ["DWH_LOADER_URL"], autocommit=True) as conn:
                if args.reiniciar:
                    _recargar(conn, tablas)
                for t in tablas:
                    inicio = datetime.now(UTC)
                    try:
                        n = _cargar_tabla(api, conn, t, instante)
                        print(f"{t['tabla']}: {n} filas")
                    except (httpx.HTTPError, psycopg.Error) as exc:
                        errores += 1
                        motivo = f"{type(exc).__name__}: {str(exc)[:300]}"
                        print(f"ERROR {t['tabla']}: {motivo}", file=sys.stderr)
                        with conn.transaction():
                            registrar(conn, t["tabla"], inicio, None, "error", {"error": motivo})
                    except Recargar:
                        _recargar(conn, tablas)
                        print(
                            "AVISO: el profesor ha vuelto a sembrar el PMS; raw_lab y sus cursores "
                            "se han vaciado: vuelve a ejecutar la carga.",
                            file=sys.stderr,
                        )
                        return SALIDA_RECARGA
    except (NotImplementedError, TokenNoValido) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return SALIDA_ERROR
    except (httpx.HTTPError, psycopg.Error) as exc:
        print(f"ERROR: {type(exc).__name__}: {str(exc)[:300]}", file=sys.stderr)
        return SALIDA_ERROR
    return SALIDA_ERROR if errores else 0


if __name__ == "__main__":
    sys.exit(main())
