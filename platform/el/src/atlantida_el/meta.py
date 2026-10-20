"""Registro de cargas en meta.carga (contrato C4): una fila por tabla y ejecución."""

from __future__ import annotations

import json

import psycopg

from .errores import CambioDeOrigen, DwhSinMigrar, error_de_conexion

ESTADOS_FINALES = ("ok", "error", "instantanea")


def _conectar(url_dwh: str) -> psycopg.Connection:
    try:
        return psycopg.connect(url_dwh, autocommit=True, connect_timeout=10)
    except psycopg.OperationalError as exc:
        raise error_de_conexion("el DWH", exc, "LOADER_PASSWORD") from None


def comprobar(url_dwh: str) -> None:
    with _conectar(url_dwh) as c:
        listo = c.execute(
            "select to_regclass('meta.carga') is not null "
            "and to_regnamespace('raw_pms_staging') is not null"
        ).fetchone()[0]
    if not listo:
        raise DwhSinMigrar("El DWH no tiene los esquemas de esta versión: ejecuta make migrar.")


def abrir(url_dwh: str, fuente: str, tabla: str) -> int:
    with _conectar(url_dwh) as c:
        return c.execute(
            "insert into meta.carga (fuente, tabla, estado) values (%s, %s, 'en_curso') "
            "returning id",
            (fuente, tabla),
        ).fetchone()[0]


def cerrar(url_dwh: str, id_: int, estado: str, filas: int | None, detalle: dict) -> None:
    if estado not in ESTADOS_FINALES:
        raise ValueError(f"estado final no válido: {estado!r} (uno de {ESTADOS_FINALES})")
    with _conectar(url_dwh) as c:
        c.execute(
            "update meta.carga set fin = now(), estado = %s, filas = %s, detalle = %s::jsonb "
            "where id = %s",
            (estado, filas, json.dumps(detalle, default=str, ensure_ascii=False), id_),
        )


def comprobar_origen(url_dwh: str, origen: str, reiniciar: bool = False) -> None:
    """Mezclar orígenes en raw_pms sin empezar de cero dejaría filas y cursores incoherentes. El
    origen de la última carga correcta se lee de meta.carga (vive en el DWH, como los datos)."""
    if reiniciar:
        return
    with _conectar(url_dwh) as c:
        fila = c.execute(
            "select fuente from meta.carga where fuente in ('pms', 'api') and estado = 'ok' "
            "order by id desc limit 1"
        ).fetchone()
    if fila and fila[0] != origen:
        raise CambioDeOrigen(
            f"raw_pms se cargó desde el origen «{fila[0]}» y ahora se pide «{origen}»: para "
            f"cambiar de origen hay que empezar de cero (make el ORIGEN={origen} REINICIAR=1). "
            "Si no querías cambiar de origen, revisa ORIGEN_PMS en platform/.env antes."
        )


AVISO_RATE_SHOPPER = (
    "AVISO: el rate shopper no respondió; las tarifas de mercado no se han actualizado y se "
    "reintentará en la próxima carga (detalle en meta.carga o con atlantida-el estado)."
)


FALLO_SIN_RS_URL = "sin RS_URL: pide al profesor la URL del rate shopper"
AVISO_SIN_RS_URL = (
    "AVISO: sin RS_URL no se cargan las tarifas de mercado (compset_diario y rate_shopper "
    "quedan vacías); pide al profesor la URL del rate shopper y ponla en RS_URL de platform/.env."
)


def aviso_rate_shopper(url_dwh: str) -> str | None:
    """El aviso si la última carga de alguna tabla del rate shopper terminó en error (uno propio
    si fue porque falta RS_URL en la edición del alumnado)."""
    vistas: set[str] = set()
    aviso = None
    for f in ultimas(url_dwh, 30):  # de la más reciente a la más antigua
        if f["tabla"] in ("compset_diario", "rate_shopper") and f["tabla"] not in vistas:
            vistas.add(f["tabla"])
            if f["estado"] == "error":
                if FALLO_SIN_RS_URL in ((f.get("detalle") or {}).get("fallos") or []):
                    return AVISO_SIN_RS_URL
                aviso = AVISO_RATE_SHOPPER
    return aviso


def ultimas(url_dwh: str, limite: int = 30) -> list[dict]:
    with _conectar(url_dwh) as c:
        cur = c.execute(
            "select id, fuente, tabla, inicio, fin, filas, estado, detalle from meta.carga "
            "order by id desc limit %s",
            (limite,),
        )
        nombres = [d.name for d in cur.description]
        return [dict(zip(nombres, f, strict=True)) for f in cur.fetchall()]
