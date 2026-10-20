"""Origen «pms»: lectura incremental del PMS local con dlt (sql_database).

Cada tabla con clave sin nulos se lee con un cursor incremental sobre updated_at (dlt guarda el
último valor en su estado, dentro del propio DWH) y se escribe con merge por la clave: una fila
nueva se inserta y una fila cambiada sustituye a la anterior. Las tablas cuya clave admite nulos
se vuelven a leer enteras (replace): son pequeñas y un NULL no casa en un merge.

Limitaciones conocidas: una transacción larga que fije updated_at al empezar y confirme después de
que la carga haya leído un valor mayor no se vuelve a leer, y los DELETE del PMS no se propagan."""

from __future__ import annotations

import functools
from datetime import datetime

import dlt
import pyarrow as pa
from dlt.sources.sql_database import sql_table

from .esquema import TablaOrigen


def con_columnas_de_carga(item, instante: datetime, origen: str):
    """Añade _loaded_at y _origen a lo que entrega dlt (tabla Arrow, fila o lista de filas)."""
    if isinstance(item, pa.Table):
        n = item.num_rows
        return item.append_column(
            "_loaded_at", pa.array([instante] * n, pa.timestamp("us", tz="UTC"))
        ).append_column("_origen", pa.array([origen] * n, pa.string()))
    if isinstance(item, dict):
        return {**item, "_loaded_at": instante, "_origen": origen}
    return [{**f, "_loaded_at": instante, "_origen": origen} for f in item]


def _anotar(item, meta=None, *, instante: datetime):
    return con_columnas_de_carga(item, instante, "pms")


@dlt.source(name="pms", max_table_nesting=0)
def fuente_pms(url_pms: str, tablas: dict[str, TablaOrigen], instante: datetime):
    credenciales = url_pms.replace("postgresql://", "postgresql+psycopg2://", 1)
    for t in tablas.values():
        incremental = dlt.sources.incremental("updated_at") if t.disposicion == "merge" else None
        r = sql_table(
            credentials=credenciales,
            table=t.nombre,
            schema="public",
            incremental=incremental,
            backend="pyarrow",
            chunk_size=50_000,
            reflection_level="minimal",
        )
        r.apply_hints(
            write_disposition=t.disposicion,
            primary_key=list(t.clave) if t.disposicion == "merge" else None,
            columns=t.hints(),
        )
        # (dlt llama a la función de map con (item, meta): un parámetro por defecto recibiría meta)
        yield r.add_map(functools.partial(_anotar, instante=instante))
