"""Orquestación mínima del almacén (la orquestación completa, con Dagster, llega después):
- pipeline: carga incremental (PMS y fuentes externas) y dbt build; repetible sin duplicar.
- historico: reconstruye el PMS desde el primer mes y lo avanza paso a paso cargando y haciendo
  dbt snapshot en cada paso, para que las dimensiones SCD2 tengan toda su historia. Borra el PMS
  (lo vuelve a sembrar) y el DWH cargado."""

from __future__ import annotations

import calendar
import hashlib
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import date
from urllib.parse import quote, unquote, urlsplit

import psycopg
from atlantida_def.edicion import del_simulador, requiere_simulador
from atlantida_el import meta
from atlantida_el.cerrojo import cerrojo
from atlantida_el.config import ConfigEL
from atlantida_el.errores import ErrorDeCarga
from atlantida_el.pipeline import cargar_externas, cargar_pms
from psycopg import sql

from . import sal
from .ejecutar import dbt
from .rutas import PROYECTO

PASOS = {"mes": 1, "trimestre": 3, "semestre": 6}
FUENTE_HISTORICO = "historico"  # fuente de la marca en meta.carga
SELECCION_IA = "source:ml+"
MODELOS_TRAS_IA = 12  # modelos que dependen de las salidas de IA (test_dbt_tramos lo comprueba)
FUENTE_TRAMO_IA = "tramo_ia"  # fuente de la huella del segundo tramo en meta.carga
# Lo que lee el segundo tramo, directa o indirectamente: las fuentes de dbt y el código.
ESQUEMAS_ENTRADA = ("raw_pms", "raw_ext", "ml")
TABLAS_ENTRADA = ("meta.modelo_ia",)
CODIGO_DBT = ("dbt_project.yml", "models", "macros", "snapshots", "seeds", "pruebas")
_SIN_HUELLA = ("_loaded_at", "_dlt_load_id", "_dlt_id")  # cambian al recargar lo mismo


class DestinoNoSeguro(ErrorDeCarga):
    """Falta un dato de conexión, los destinos no coinciden o el simulador vivo está en marcha."""


class HistoricoIncompleto(ErrorDeCarga):
    """Hay un historico empezado que no terminó bien: el almacén puede tener SCD2 truncadas."""


def _prod(entorno: Mapping[str, str] | None) -> dict[str, str]:
    """Los caminos de producción construyen siempre en prod, diga lo que diga DBT_TARGET del
    entorno del llamador: solo `make dbt ENTORNO=dev` trabaja en los esquemas dev_*."""
    return {**(entorno or {}), "DBT_TARGET": "prod"}


def url_transformer(entorno: Mapping[str, str] = os.environ) -> str:
    return (
        f"postgresql://{quote(entorno.get('TRANSFORMER_USER', 'transformer'), safe='')}:"
        f"{quote(entorno.get('TRANSFORMER_PASSWORD', ''), safe='')}@"
        f"{entorno.get('DWH_HOST', '127.0.0.1')}:"
        f"{entorno.get('DWH_PORT_INTERNO') or entorno.get('DWH_PORT') or '5434'}/"
        f"{quote(entorno.get('DWH_DB', 'dwh'), safe='')}"
    )


def _normal(host: str | None) -> str:
    return "127.0.0.1" if host in (None, "", "localhost", "::1") else host


def _destino_url(url: str, nombre: str) -> tuple[str, str, str]:
    p = urlsplit(url or "")
    base = unquote(p.path.lstrip("/"))
    if not (p.hostname and p.port and base):
        raise DestinoNoSeguro(
            f"Falta o está incompleta la conexión a {nombre} "
            "(se necesita servidor, puerto y base). "
            "Revisa platform/.env; no se usa ningún valor por omisión."
        )
    return _normal(p.hostname), str(p.port), base


def destinos(
    config_sim, config_el: ConfigEL, entorno: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Destinos de la reconstrucción como «servidor:puerto/base» (sin usuario ni clave).
    Falla si falta algún dato de conexión o si dos referencias al mismo almacén no coinciden."""
    from psycopg.conninfo import conninfo_to_dict

    env = {**os.environ, **(entorno or {})}
    if not config_sim.dsn:
        raise DestinoNoSeguro(
            "Falta la conexión al PMS del simulador: define PMS_DB, PMS_USER, PMS_PASSWORD "
            "(y PMS_HOST) en platform/.env."
        )
    d = conninfo_to_dict(config_sim.dsn)
    sim = (_normal(d.get("host")), str(d.get("port") or ""), d.get("dbname") or "")
    if not all(sim):
        raise DestinoNoSeguro("La conexión al PMS del simulador está incompleta.")
    el_pms = _destino_url(config_el.url_pms, "el PMS (carga)")
    el_dwh = _destino_url(config_el.url_dwh, "el DWH (carga)")
    for var, texto in (
        ("DWH_DB", "la base del DWH"),
        ("TRANSFORMER_PASSWORD", "la clave del rol transformer"),
    ):
        if not env.get(var):
            raise DestinoNoSeguro(f"Falta {var} ({texto}); no se usa ningún valor por omisión.")
    if not (env.get("DWH_PORT_INTERNO") or env.get("DWH_PORT")):
        raise DestinoNoSeguro("Falta DWH_PORT: no se usa ningún puerto por omisión.")
    transformer = _destino_url(url_transformer(env), "el DWH (transformer)")
    if sim != el_pms:
        raise DestinoNoSeguro(
            f"El PMS que siembra el simulador ({_fmt(sim)}) no es el que lee la carga "
            f"({_fmt(el_pms)}). Revisa PMS_HOST, PMS_PORT y PMS_DB."
        )
    if transformer != el_dwh:
        raise DestinoNoSeguro(
            f"El DWH de dbt ({_fmt(transformer)}) no es el de la carga ({_fmt(el_dwh)}). "
            "Revisa DWH_HOST, DWH_PORT y DWH_DB."
        )
    return {"pms": _fmt(sim), "dwh": _fmt(el_dwh)}


def _fmt(t: tuple[str, str, str]) -> str:
    return f"{t[0]}:{t[1]}/{t[2]}"


def aviso_historico(objetivos: dict[str, str] | None = None, escala: float | None = None) -> str:
    destino = (
        f"\nDestino: PMS {objetivos['pms']}; DWH {objetivos['dwh']}."
        if objetivos
        else "\nDestino: sin determinar (revisa la conexión)."
    )
    if escala is not None:
        destino += f"\nEscala: {escala:g} (SIM_ESCALA o make historico ESCALA=…)."
    return (
        "historico borra y reconstruye, sin posibilidad de deshacer:\n"
        "  - todos los datos del PMS (se vuelve a sembrar);\n"
        "  - los datos que haya escrito el ETL inverso (guest_flag, rate_restriction…);\n"
        "  - la historia SCD2 acumulada (snapshots snp_*);\n"
        "  - y recarga el DWH (raw_pms y fuentes externas) desde cero."
        + destino
        + "\nA escala 1 tarda decenas de minutos (usa --paso trimestre para acortarlo)."
    )


def vivo_activo(config_sim, espera: float | None = None) -> bool:
    """El simulador vivo no deja cerrojo: se detecta porque el reloj del PMS (sim.reloj) avanza
    mientras se observa. Se mira durante algo más que un paso del vivo."""
    leer_reloj = del_simulador("carga", "make historico").leer_reloj
    periodo_tick = del_simulador("vivo", "make historico").periodo_tick

    if espera is None:
        espera = min(
            periodo_tick(config_sim, None) + config_sim.segundos_por_dia / 1440 + 1.5, 90.0
        )
    with psycopg.connect(config_sim.dsn, autocommit=True) as c:
        antes = leer_reloj(c)
        if antes is None:
            return False
        time.sleep(espera)
        despues = leer_reloj(c)
    return despues is not None and (despues["corte"], despues["epoca"]) != (
        antes["corte"],
        antes["epoca"],
    )


def comprobar_sin_historico_abierto(url_dwh: str) -> None:
    with meta._conectar(url_dwh) as c:
        fila = c.execute(
            "select id, estado from meta.carga where fuente = %s order by id desc limit 1",
            (FUENTE_HISTORICO,),
        ).fetchone()
    if fila and fila[1] != "ok":
        raise HistoricoIncompleto(
            f"La última reconstrucción histórica (id {fila[0]}) quedó «{fila[1]}»: el almacén "
            "puede tener las SCD2 incompletas. Repite `atlantida-dbt historico --confirmar` "
            "(make historico) antes de usar pipeline."
        )


def comprobar_previo(
    config_el: ConfigEL, reiniciar: bool = False, entorno: Mapping[str, str] | None = None
) -> bool:
    """Antes de cargar: ninguna reconstrucción histórica a medias y la sal es la de la última
    construcción. True si la sal ha cambiado y se acepta porque se reinicia. La usan pipeline y
    los assets de Dagster."""
    comprobar_sin_historico_abierto(config_el.url_dwh)
    return sal.comprobar(config_el.url_dwh, {**os.environ, **(entorno or {})}, reiniciar)


def argumentos_build(sal_nueva: bool, entorno: Mapping[str, str] | None = None) -> list[str]:
    """La orden de dbt tras cargar: con otra sal, las fichas con seudónimos se rehacen desde
    cero."""
    if not sal_nueva:
        return ["build"]
    with psycopg.connect(url_transformer({**os.environ, **(entorno or {})}), autocommit=True) as c:
        c.execute("drop table if exists snapshots.snp_huespedes")
    return ["build", "--full-refresh"]


def _huella_codigo(h) -> None:
    from importlib.metadata import version

    h.update(version("dbt-core").encode())
    for raiz in CODIGO_DBT:
        ruta = PROYECTO / raiz
        for f in sorted([ruta] if ruta.is_file() else ruta.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                h.update(str(f.relative_to(PROYECTO)).encode() + b"\0" + f.read_bytes())


def resumen_entradas_ia(entorno: Mapping[str, str] | None = None) -> dict:
    """Resumen de cada tabla que lee el segundo tramo: {(esquema, tabla): (columnas, valores)}.

    Se resume el contenido sin las columnas de carga: las instantáneas, las tablas del PMS que se
    reemplazan en cada carga y el repaso del rate shopper vuelven a cargar las mismas filas. En las
    tablas del PMS que se cargan de forma incremental (filas de cargas distintas) basta el número
    de filas y la última carga (_loaded_at): la carga solo toca las filas que cambian."""
    resumen = {}
    with psycopg.connect(url_transformer({**os.environ, **(entorno or {})})) as c:
        columnas: dict[tuple[str, str], list[str]] = {}
        for esquema, tabla, columna in c.execute(
            "select c.table_schema, c.table_name, c.column_name from information_schema.columns c "
            "join information_schema.tables t using (table_schema, table_name) "
            "where t.table_type = 'BASE TABLE' and left(c.table_name, 4) <> '_dlt' "
            "and (c.table_schema = any(%s) or c.table_schema || '.' || c.table_name = any(%s)) "
            "order by 1, 2, c.ordinal_position",
            (list(ESQUEMAS_ENTRADA), list(TABLAS_ENTRADA)),
        ).fetchall():
            columnas.setdefault((esquema, tabla), []).append(columna)
        for (esquema, tabla), cols in sorted(columnas.items()):
            nombre = sql.Identifier(esquema, tabla)
            if esquema == "raw_pms" and "_loaded_at" in cols:
                n, ultima, primera = c.execute(
                    sql.SQL(
                        "select count(*), max(_loaded_at)::text, min(_loaded_at)::text from {}"
                    ).format(nombre)
                ).fetchone()
                if primera != ultima:  # filas de varias cargas: incremental
                    resumen[(esquema, tabla)] = (tuple(cols), (n, ultima))
                    continue
            fila = sql.SQL(", ").join(sql.Identifier(x) for x in cols if x not in _SIN_HUELLA)
            q = sql.SQL(
                "select count(*), sum(hashtextextended(row({})::text, 0))::text from {}"
            ).format(fila, nombre)
            resumen[(esquema, tabla)] = (tuple(cols), c.execute(q).fetchone())
    return resumen


def huella_entradas_ia(entorno: Mapping[str, str] | None = None) -> str:
    """Huella de todo lo que lee el segundo tramo (lo que depende de ml): el código de dbt y el
    contenido de sus fuentes (raw_pms, raw_ext, ml y la ficha del modelo oficial; ver
    resumen_entradas_ia). Con la misma huella que en la última construcción, el segundo tramo
    reconstruiría lo mismo."""
    h = hashlib.sha256()
    _huella_codigo(h)
    h.update(repr(sorted(resumen_entradas_ia(entorno).items())).encode())
    return h.hexdigest()


def huella_ia_guardada(url_dwh: str) -> str | None:
    with meta._conectar(url_dwh) as c:
        fila = c.execute(
            "select detalle->>'huella' from meta.carga where fuente = %s and estado = 'ok' "
            "order by id desc limit 1",
            (FUENTE_TRAMO_IA,),
        ).fetchone()
    return fila[0] if fila else None


def registrar_huella_ia(url_dwh: str, huella: str) -> None:
    marca = meta.abrir(url_dwh, FUENTE_TRAMO_IA, "segundo_tramo")
    meta.cerrar(url_dwh, marca, "ok", None, {"huella": huella})


def pipeline(
    config_el: ConfigEL,
    reiniciar: bool = False,
    entorno: dict | None = None,
    cliente_api=None,
    cliente_rs=None,
    espera_cerrojo: float = 1800.0,
    entre_tramos: Callable[[], None] | None = None,
) -> None:
    """Carga incremental y dbt build bajo el cerrojo. Con entre_tramos (la IA): primero todo lo
    que no depende de ml, después entre_tramos() y por último lo que depende de ml, con las mismas
    opciones (p. ej. --full-refresh). Un solo cerrojo para todo: entre_tramos no debe tomarlo.

    El segundo tramo se omite si sus entradas (huella_entradas_ia: reseñas clasificadas, ficha
    del modelo oficial, datos cargados y código de dbt) son las de su última construcción, salvo
    con reiniciar o con una sal nueva."""
    with cerrojo(config_el.url_dwh, espera_cerrojo):
        sal_nueva = comprobar_previo(config_el, reiniciar, entorno)
        cargar_pms(config_el, reiniciar=reiniciar, cliente_api=cliente_api)
        cargar_externas(config_el, reiniciar=reiniciar, cliente_rs=cliente_rs)
        args = argumentos_build(sal_nueva, entorno)
        if entre_tramos is None:
            dbt(args, entorno=_prod(entorno))
        else:
            dbt([*args, "--exclude", SELECCION_IA], entorno=_prod(entorno))
            entre_tramos()
            huella = huella_entradas_ia(entorno)
            if (
                not reiniciar
                and args == ["build"]
                and huella == huella_ia_guardada(config_el.url_dwh)
            ):
                print(
                    "Lo que depende de la IA ya está al día (sin reseñas nuevas, el mismo modelo "
                    "oficial y los mismos datos y código): se omite el segundo tramo de dbt.",
                    flush=True,
                )
            else:
                dbt([*args, "--select", SELECCION_IA], entorno=_prod(entorno))
                registrar_huella_ia(config_el.url_dwh, huella)
        sal.registrar(config_el.url_dwh, {**os.environ, **(entorno or {})})


def _fin_de_mes(anio: int, mes: int) -> date:
    return date(anio, mes, calendar.monthrange(anio, mes)[1])


def cortes_historicos(inicio: date, fin: date, paso: str) -> list[date]:
    meses = PASOS[paso]
    cortes = [_fin_de_mes(inicio.year, inicio.month)]
    while True:
        indice = cortes[-1].year * 12 + cortes[-1].month - 1 + meses
        siguiente = _fin_de_mes(indice // 12, indice % 12 + 1)
        if siguiente >= fin:
            break
        cortes.append(siguiente)
    if cortes[-1] < fin:
        cortes.append(fin)
    return cortes


def historico(
    config_sim,
    config_el: ConfigEL,
    paso: str = "mes",
    hasta: date | None = None,
    construir: bool = True,
    entorno: dict | None = None,
    cliente_rs=None,
    historia=None,
    avisar: Callable[[str], None] = print,
    espera_vivo: float | None = None,
    espera_cerrojo: float = 1800.0,
) -> list[date]:
    requiere_simulador("make historico")
    objetivos = destinos(config_sim, config_el, entorno)
    if vivo_activo(config_sim, espera_vivo):
        raise DestinoNoSeguro(
            "El simulador vivo está en marcha (el reloj del PMS avanza): páralo con "
            "make vivo-parar antes de reconstruir el histórico."
        )
    # Lo anterior solo lee; desde aquí se escribe en el almacén.
    with cerrojo(config_el.url_dwh, espera_cerrojo, avisar=avisar):
        avisar(aviso_historico(objetivos, config_sim.escala))
        marca = meta.abrir(config_el.url_dwh, FUENTE_HISTORICO, "dwh")
        try:
            cortes = _reconstruir(
                config_sim, config_el, paso, hasta, construir, entorno, cliente_rs, historia, avisar
            )
        except BaseException as exc:
            meta.cerrar(config_el.url_dwh, marca, "error", None, {"error": str(exc)[:500]})
            avisar(
                "histórico: reconstrucción incompleta; repite historico --confirmar "
                "(make historico)."
            )
            raise
        meta.cerrar(config_el.url_dwh, marca, "ok", len(cortes), {"cortes": len(cortes)})
    return cortes


def _reconstruir(
    config_sim, config_el, paso, hasta, construir, entorno, cliente_rs, historia, avisar
) -> list[date]:
    sim_carga = del_simulador("carga", "make historico")
    avanzar, sembrar = sim_carga.avanzar, sim_carga.sembrar
    generar = del_simulador("motor", "make historico").generar
    fin_de_dia = del_simulador("tiempo", "make historico").fin_de_dia

    # Se reconstruye el PMS local: la carga sale de él aunque .env diga ORIGEN_PMS=api.
    config_el = replace(config_el, origen="pms")
    cortes = cortes_historicos(config_sim.inicio, hasta or config_sim.fin, paso)
    h = historia if historia is not None else generar(config_sim)
    with psycopg.connect(config_sim.dsn, autocommit=True) as c:
        sembrar(config_sim, reiniciar=True, hasta=cortes[0], conn=c, historia=h)
    with psycopg.connect(url_transformer({**os.environ, **(entorno or {})}), autocommit=True) as c:
        for snp in ("snp_hoteles", "snp_huespedes", "snp_reservas"):
            c.execute(
                f"drop table if exists snapshots.{snp}"
            )  # la historia anterior es de otra siembra
    cargar_pms(config_el, reiniciar=True)
    # Las externas no tienen historia SCD2, pero el staging las lee: se cargan antes de construirlo.
    cargar_externas(config_el, reiniciar=True, cliente_rs=cliente_rs)
    dbt(["run", "--select", "staging"], entorno=_prod(entorno))
    dbt(["snapshot"], entorno=_prod(entorno))
    avisar(f"histórico: PMS sembrado hasta {cortes[0]}")
    for corte in cortes[1:]:
        with psycopg.connect(config_sim.dsn, autocommit=True) as c:
            avanzar(config_sim, fin_de_dia(corte), conn=c, historia=h)
        cargar_pms(config_el)
        dbt(["snapshot"], entorno=_prod(entorno))
        avisar(f"histórico: avanzado hasta {corte}")
    # Las externas se cargaron con el PMS en el primer corte (el rate shopper solo sirve hasta el
    # reloj de la simulación): se completan hasta el último antes de construir el almacén.
    cargar_externas(config_el, cliente_rs=cliente_rs)
    if construir:
        dbt(["build", "--full-refresh"], entorno=_prod(entorno))
        sal.registrar(config_el.url_dwh, {**os.environ, **(entorno or {})})
    return cortes
