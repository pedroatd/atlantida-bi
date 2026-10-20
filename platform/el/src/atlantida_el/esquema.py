"""Esquema de las tablas del PMS para dlt: columnas, tipos y clave de cada tabla, leídos del
catálogo de PostgreSQL (origen pms) o de /v1/tablas (origen api). Los dos caminos dan las mismas
indicaciones (hints) a dlt, de modo que raw_pms queda igual sea cual sea el origen."""

from __future__ import annotations

import re
from dataclasses import dataclass

from atlantida_def import cargar_contrato

from .errores import PmsNoSembrado

COLUMNAS_CARGA: dict[str, dict] = {
    "_loaded_at": {"data_type": "timestamp", "nullable": False},
    "_origen": {"data_type": "text", "nullable": False},
}
_TIPOS = {
    "bigint": "bigint", "integer": "bigint", "smallint": "bigint",
    "text": "text", "character varying": "text",
    "boolean": "bool", "date": "date",
    "timestamptz": "timestamp", "timestamp with time zone": "timestamp",
    "double precision": "double", "real": "double", "numeric": "decimal",
}  # fmt: skip


def tipo_dlt(tipo_sql: str) -> dict:
    t = tipo_sql.strip().lower()
    m = re.fullmatch(r"numeric\((\d+),\s*(\d+)\)", t)
    if m:
        return {"data_type": "decimal", "precision": int(m[1]), "scale": int(m[2])}
    if t not in _TIPOS:
        raise ValueError(f"tipo SQL sin correspondencia en dlt: {tipo_sql}")
    return {"data_type": _TIPOS[t]}


RELEER_ENTERAS = frozenset({"guest_flag"})
"""Tablas que el reverse ETL puede borrar (revertir una marca VIP): se releen enteras en cada
carga para que el borrado llegue al DWH (un merge incremental no ve las filas que desaparecen)."""


@dataclass(frozen=True)
class TablaOrigen:
    nombre: str
    columnas: tuple[tuple[str, str], ...]
    clave: tuple[str, ...]
    clave_con_nulos: tuple[str, ...]

    @property
    def disposicion(self) -> str:
        """merge por la clave; replace si la clave admite nulos (NULL no casa en un merge) o si
        la tabla está en RELEER_ENTERAS (sus borrados deben llegar al DWH)."""
        return "replace" if self.clave_con_nulos or self.nombre in RELEER_ENTERAS else "merge"

    def hints(self) -> dict[str, dict]:
        return {**{c: tipo_dlt(t) for c, t in self.columnas}, **COLUMNAS_CARGA}


_SQL_COLUMNAS = """
select c.relname, a.attname, format_type(a.atttypid, a.atttypmod)
from pg_attribute a
join pg_class c on c.oid = a.attrelid
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind in ('r', 'p') and a.attnum > 0 and not a.attisdropped
"""
_SQL_CLAVES = """
select c.relname,
       array(select a.attname from unnest(k.conkey) with ordinality as u(num, i)
             join pg_attribute a on a.attrelid = k.conrelid and a.attnum = u.num order by u.i),
       array(select a.attname from unnest(k.conkey) as u(num)
             join pg_attribute a on a.attrelid = k.conrelid and a.attnum = u.num
             where not a.attnotnull)
from pg_constraint k
join pg_class c on c.oid = k.conrelid
join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and k.contype in ('p', 'u')
order by c.relname, k.contype, k.conname
"""


def tablas_desde_catalogo(conn) -> dict[str, TablaOrigen]:
    """Clave = la primaria o, si no hay, la primera única (el mismo criterio que la API)."""
    contrato = cargar_contrato()
    tipos: dict[str, dict[str, str]] = {}
    for t, col, tipo in conn.execute(_SQL_COLUMNAS):
        tipos.setdefault(t, {})[col] = tipo
    faltan = [t for t in contrato if t not in tipos]
    if faltan:
        raise PmsNoSembrado(
            f"El PMS no tiene las tablas del contrato ({', '.join(faltan[:4])}…): "
            "siémbralo con make seed."
        )
    claves: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {}
    for t, cols, nulas in conn.execute(_SQL_CLAVES):
        claves.setdefault(t, (tuple(cols), tuple(nulas)))
    sin_clave = [t for t in contrato if t not in claves]
    if sin_clave:
        raise ValueError(f"tablas del PMS sin clave primaria ni única: {sin_clave}")
    return {
        t: TablaOrigen(t, tuple((c, tipos[t][c]) for c in cols), *claves[t])
        for t, cols in contrato.items()
    }


def tablas_desde_api(tablas: list[dict]) -> dict[str, TablaOrigen]:
    contrato = cargar_contrato()
    por_nombre = {t["tabla"]: t for t in tablas}
    faltan = [t for t in contrato if t not in por_nombre]
    if faltan:
        raise ValueError(f"la API no ofrece estas tablas del contrato: {faltan}")
    return {
        n: TablaOrigen(
            n,
            tuple((c["nombre"], c["tipo"]) for c in por_nombre[n]["columnas"]),
            tuple(por_nombre[n]["clave"]),
            tuple(por_nombre[n]["clave_con_nulos"]),
        )
        for n in contrato
    }
