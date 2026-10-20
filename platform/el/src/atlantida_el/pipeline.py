"""Ejecución de las cargas con dlt y registro de cada tabla en meta.carga."""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import dlt
import httpx
import psycopg
from atlantida_def import cargar_definicion
from psycopg import sql

from . import meta
from .config import ConfigEL
from .errores import (
    FALTA_SIM_API_TOKEN,
    DwhSinMigrar,
    ErrorDeCarga,
    TokenNoValido,
    causa_raiz,
    error_de_conexion,
)
from .esquema import tablas_desde_api, tablas_desde_catalogo
from .fuente_api import ClienteCambios, fuente_api
from .fuente_externa import (
    FUENTES_INSTANTANEA,
    TABLAS_RATE_SHOPPER,
    ClienteRateShopper,
    ProveedorNoDisponible,
    definiciones_externas,
    fuente_externa,
)
from .fuente_pms import fuente_pms
from .secretos import enmascarar

NOMBRE_PMS = "atlantida_pms"
NOMBRE_EXT = "atlantida_ext"


@dataclass
class ResultadoCarga:
    filas: dict[str, int] = field(default_factory=dict)
    load_ids: list[str] = field(default_factory=list)


Definicion = tuple[dict[str, dict], str, tuple[str, ...]]  # (hints, disposición, clave)


def crear_pipeline(nombre: str, dataset: str, config: ConfigEL) -> dlt.Pipeline:
    """El estado incremental vive en el DWH (_dlt_pipeline_state): en un contenedor efímero el
    estado local está vacío y sync_destination() lo recupera antes de construir la fuente.
    Crear el pipeline antes que la fuente también hace que dlt.current apunte a este pipeline."""
    pipeline = dlt.pipeline(
        pipeline_name=nombre,
        destination=dlt.destinations.postgres(credentials=config.url_dwh),
        dataset_name=dataset,
        pipelines_dir=str(config.dir_dlt),
    )
    pipeline.sync_destination()
    return pipeline


_SQL_DE_DLT = {
    "text": "varchar", "bigint": "bigint", "bool": "boolean", "date": "date",
    "timestamp": "timestamptz", "double": "double precision",
}  # fmt: skip


def _tipo_sql(hint: dict) -> str:
    if hint["data_type"] == "decimal":
        return f"numeric({hint['precision']},{hint['scale']})"
    return _SQL_DE_DLT[hint["data_type"]]


def asegurar_tablas(
    dataset: str,
    definiciones: dict[str, Definicion],
    config: ConfigEL,
) -> list[str]:
    """dlt solo crea una tabla cuando recibe filas. Las que no han recibido ninguna (tablas del
    PMS vacías, el rate shopper caído en la primera carga) se crean vacías con su esquema, porque
    staging las lee. Devuelve las creadas."""
    with psycopg.connect(config.url_dwh) as c:
        existentes = {
            t
            for (t,) in c.execute(
                "select table_name from information_schema.tables where table_schema = %s",
                (dataset,),
            )
        }
    faltan = {n: d for n, d in definiciones.items() if n not in existentes}
    if not faltan:
        return []

    # Se crean con SQL y no con dlt: una tabla que dlt materializa vacía lleva _dlt_id y
    # _dlt_load_id (NOT NULL) y las cargas Arrow posteriores no las traen. Así la tabla vacía
    # tiene exactamente las columnas de la definición, las mismas que tendrá al recibir filas.
    with psycopg.connect(config.url_dwh) as c:
        for nombre, (hints, _disposicion, clave) in faltan.items():
            columnas = sql.SQL(", ").join(
                sql.SQL("{} {}{}").format(
                    sql.Identifier(col),
                    sql.SQL(_tipo_sql(h)),
                    # dlt marca NOT NULL las columnas de la clave primaria de las tablas merge
                    sql.SQL("" if h.get("nullable", True) and col not in clave else " not null"),
                )
                for col, h in hints.items()
            )
            c.execute(
                sql.SQL("create table if not exists {}.{} ({})").format(
                    sql.Identifier(dataset), sql.Identifier(nombre), columnas
                )
            )
    return sorted(faltan)


def analizar(dataset: str, config: ConfigEL) -> None:
    """ANALYZE de las tablas recién cargadas: sin estadísticas, el planificador puede elegir un
    plan pésimo en el primer dbt tras una carga (el autovacuum aún no ha pasado)."""
    with psycopg.connect(config.url_dwh, autocommit=True) as c:
        tablas = [
            t
            for (t,) in c.execute(
                "select tablename from pg_tables where schemaname = %s and tablename !~ '^_dlt'",
                (dataset,),
            )
        ]
        for t in tablas:
            c.execute(sql.SQL("analyze {}.{}").format(sql.Identifier(dataset), sql.Identifier(t)))


def contar_filas(dataset: str, tablas: Iterable[str], config: ConfigEL) -> dict[str, int]:
    """Recuento de cada tabla raw tras la carga: el check de volumen de Dagster lo compara con el
    de la carga anterior (una tabla raw solo pierde filas si se reinicia)."""
    with psycopg.connect(config.url_dwh) as c:
        existentes = {
            t
            for (t,) in c.execute(
                "select tablename from pg_tables where schemaname = %s", (dataset,)
            )
        }
        return {
            t: c.execute(
                sql.SQL("select count(*) from {}.{}").format(
                    sql.Identifier(dataset), sql.Identifier(t)
                )
            ).fetchone()[0]
            for t in tablas
            if t in existentes
        }


def _ejecutar(
    pipeline: dlt.Pipeline,
    fuente,
    tablas: list[str],
    fuente_meta: str,
    config: ConfigEL,
    reiniciar: bool,
    estado_de: Callable[[str], str] = lambda t: "ok",
    detalle_de: Callable[[str], dict] = lambda t: {},
    definiciones: dict[str, Definicion] | None = None,
) -> ResultadoCarga:
    ids = {t: meta.abrir(config.url_dwh, fuente_meta, t) for t in tablas}
    try:
        # reiniciar: vacía las tablas y el estado incremental (drop_data, no DROP TABLE: las vistas
        # de staging dependen de ellas y una resiembra del profesor no debe romper el almacén).
        info = pipeline.run(
            fuente, refresh="drop_data" if reiniciar else None, loader_file_format="csv"
        )
        normalizado = pipeline.last_trace.last_normalize_info
        cuentas = normalizado.row_counts if normalizado else {}
        res = ResultadoCarga({t: int(cuentas.get(t, 0)) for t in tablas}, list(info.loads_ids))
        if definiciones:
            asegurar_tablas(pipeline.dataset_name, definiciones, config)
        analizar(pipeline.dataset_name, config)
        totales = contar_filas(pipeline.dataset_name, tablas, config)
    except Exception as exc:
        raiz = causa_raiz(exc)
        texto = enmascarar(str(raiz), os.environ)
        for i in ids.values():
            meta.cerrar(config.url_dwh, i, "error", None, {"error": texto[:500]})
        if type(raiz).__name__ == "InsufficientPrivilege":
            raise DwhSinMigrar(
                f"El rol loader no tiene permisos en el DWH ({texto.splitlines()[0]}): "
                "ejecuta make migrar."
            ) from exc
        if isinstance(raiz, ErrorDeCarga):
            raise raiz from exc
        raise
    for t, i in ids.items():
        detalle = {
            "pipeline": pipeline.pipeline_name,
            "load_ids": res.load_ids,
            "reiniciar": reiniciar,
            **({"filas_tabla": totales[t]} if t in totales else {}),
            **detalle_de(t),
        }
        meta.cerrar(config.url_dwh, i, estado_de(t), res.filas[t], detalle)
    return res


def _tablas_pms(config: ConfigEL):
    try:
        with psycopg.connect(config.url_pms, connect_timeout=10) as c:
            return tablas_desde_catalogo(c)
    except psycopg.OperationalError as exc:
        raise error_de_conexion("el PMS", exc, config.variable_clave_pms) from None


def _definiciones(tablas) -> dict[str, Definicion]:
    return {
        n: (t.hints(), t.disposicion, t.clave if t.disposicion == "merge" else ())
        for n, t in tablas.items()
    }


def cargar_pms(
    config: ConfigEL, reiniciar: bool = False, cliente_api: httpx.Client | None = None
) -> ResultadoCarga:
    """Carga incremental del PMS en raw_pms desde el origen configurado (pms o api). El orden
    importa: comprobar el origen (meta.carga), crear el pipeline y recuperar su estado del DWH,
    y solo entonces construir la fuente."""
    meta.comprobar(config.url_dwh)
    meta.comprobar_origen(config.url_dwh, config.origen, reiniciar)
    instante = datetime.now(UTC)
    detalle: dict = {}
    if config.origen == "api":
        cliente = ClienteCambios(config.api_url, config.api_token, cliente_api)
        try:
            tablas = tablas_desde_api(cliente.tablas())
        except TokenNoValido:
            # Una API local sin token es válida (make servir); si pide token y no hay, se dice.
            if not config.api_token:
                raise TokenNoValido(FALTA_SIM_API_TOKEN) from None
            raise
        hasta = cliente.corte()
        pipeline = crear_pipeline(NOMBRE_PMS, "raw_pms", config)
        fuente = fuente_api(cliente, tablas, instante, hasta)
        detalle = {"hasta": hasta}  # corte de esta sincronización: filas con updated_at < hasta
    else:
        tablas = _tablas_pms(config)
        pipeline = crear_pipeline(NOMBRE_PMS, "raw_pms", config)
        fuente = fuente_pms(config.url_pms, tablas, instante)
    return _ejecutar(
        pipeline,
        fuente,
        list(tablas),
        config.origen,
        config,
        reiniciar,
        detalle_de=lambda t: detalle,
        definiciones=_definiciones(tablas),
    )


def cargar_externas(
    config: ConfigEL,
    reiniciar: bool = False,
    cliente_rs: httpx.Client | None = None,
    dormir: Callable[[float], None] = time.sleep,
) -> ResultadoCarga:
    """Instantáneas externas (replace) y rate shopper (merge incremental con repaso)."""
    meta.comprobar(config.url_dwh)
    instante = datetime.now(UTC)
    calidad: dict[str, dict] = {t: {} for t in TABLAS_RATE_SHOPPER}
    rs: ClienteRateShopper | None = None
    corte = None
    if config.rate_shopper_url is None:
        # Edición del alumnado sin RS_URL: no hay rate shopper al que llamar; se anota y siguen
        # las instantáneas.
        for c in calidad.values():
            c.setdefault("fallos", []).append(meta.FALLO_SIN_RS_URL)
    else:
        rs = ClienteRateShopper(
            config.rate_shopper_url,
            cliente_rs,
            reintentos=config.reintentos_rs,
            dormir=dormir,
            token=config.rs_token,
        )
        try:
            corte = rs.corte()
            if corte is None:
                raise ProveedorNoDisponible("el rate shopper no tiene datos todavía (¿make seed?)")
        except ProveedorNoDisponible as exc:
            corte = None
            for c in calidad.values():
                c.setdefault("fallos", []).append(str(exc))
    desde = cargar_definicion().horizonte_simulado.inicio
    pipeline = crear_pipeline(NOMBRE_EXT, "raw_ext", config)
    fuente = fuente_externa(rs, corte, desde, config.tarifas_desde or desde, instante, calidad)

    def estado_de(t: str) -> str:
        if t in FUENTES_INSTANTANEA:
            return "instantanea"
        return "error" if calidad[t].get("fallos") else "ok"

    return _ejecutar(
        pipeline,
        fuente,
        [*FUENTES_INSTANTANEA, *TABLAS_RATE_SHOPPER],
        "externa",
        config,
        reiniciar,
        estado_de=estado_de,
        detalle_de=lambda t: calidad.get(t, {}),
        definiciones=definiciones_externas(),
    )
