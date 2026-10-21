"""Comprobador del modelo dimensional de tu proyecto (make comprobar). Lee modelo.yml, lo que
declaras de tu modelo, y mira en tu base «proyecto», tal como la ha dejado dbt:

- que cada hecho cumple su grano (ninguna combinación de sus columnas se repite);
- que sus claves foráneas son enteras y no tienen huérfanos (el desconocido es −1, nunca un
  nulo, salvo en una clave «opcional») y, hacia una SCD2 con «fecha», que apuntan a la versión
  vigente en esa fecha;
- que cada dimensión tiene su clave sustituta entera y única y su miembro desconocido (−1), salvo
  si declara «miembro_desconocido: false», y que su clave natural, si la declara, no se repite;
- en las dimensiones SCD2, exactamente una versión vigente por clave natural e intervalos
  [desde, hasta) no vacíos y sin solape;
- que ninguna columna de «personales» del contrato del L3 está en claro fuera de raw.

Avisa, sin fallar, si muchas filas de un hecho van al desconocido de una dimensión (solo da la
proporción) y si hay huecos entre las versiones de una SCD2. No mira cifras: un modelo correcto
pasa con cualquier volumen de datos y sin historia."""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ESQUEMA_POR_OMISION = "marts"
# Esquemas que no son del modelo: la carga del L3 (raw y meta, y el raw_staging de dlt).
FUERA_DEL_MODELO = ("raw", "raw_staging", "meta", "information_schema")
# Claves sustitutas de los miembros especiales: −1 desconocido, −2 «no aplica» (cap. 8).
ESPECIALES = (-1, -2)
ENTEROS = ("smallint", "integer", "bigint")


class ModeloNoValido(ValueError):
    """modelo.yml no declara lo que hace falta para comprobar el modelo."""


@dataclass(frozen=True)
class Scd2:
    clave_natural: tuple[str, ...]
    desde: str
    hasta: str
    origen: str


@dataclass(frozen=True)
class Hecho:
    nombre: str
    esquema: str
    grano: tuple[str, ...]
    claves_foraneas: dict[str, str] = field(default_factory=dict)  # columna → dimensión
    # Claves foráneas que pueden ser nulas por diseño (columna → motivo): un rol opcional.
    opcionales: dict[str, str] = field(default_factory=dict)
    # Claves foráneas hacia una SCD2 con la columna del hecho que elige su versión.
    fechas: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Dimension:
    nombre: str
    esquema: str
    clave_sustituta: str
    scd2: Scd2 | None = None
    miembro_desconocido: bool = True  # False (con su motivo): un calendario completo, sin −1
    clave_natural: tuple[str, ...] | None = None  # solo en las de tipo 1 (la SCD2, en scd2)


@dataclass(frozen=True)
class Modelo:
    hechos: tuple[Hecho, ...]
    dimensiones: tuple[Dimension, ...]
    contrato: dict  # tablas del contrato del L3: nombre → definición
    personales: dict[str, tuple[str, ...]]
    # Tabla de raw → estrategias de los snapshots que la leen (de snapshots/*.yml del kit).
    estrategias: dict[str, frozenset[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class Hallazgo:
    nivel: str  # error, aviso u ok
    objeto: str  # tabla o tabla.columna
    mensaje: str

    def __str__(self) -> str:
        return f"{self.nivel.upper()} {self.objeto}: {self.mensaje}"


# --- modelo.yml ---


def _mapa(donde: str, valor, campo: str) -> dict:
    if valor is None:
        return {}
    if not isinstance(valor, dict):
        raise ModeloNoValido(f"{donde}: «{campo}» debe ser un mapa nombre → definición")
    return valor


def _columnas(donde: str, valor) -> tuple[str, ...]:
    if isinstance(valor, str) or not isinstance(valor, list) or not valor:
        raise ModeloNoValido(f"{donde}: una lista de columnas, p. ej. [id, fecha]")
    if not all(isinstance(c, str) and c for c in valor):
        raise ModeloNoValido(f"{donde}: una lista de columnas (nombres de texto)")
    return tuple(valor)


def _texto(donde: str, d: dict, campo: str) -> str:
    valor = d.get(campo)
    if not valor:
        raise ModeloNoValido(f"{donde}: falta «{campo}»")
    if not isinstance(valor, str):
        raise ModeloNoValido(f"{donde}.{campo}: el nombre de una columna")
    return valor


def _sin_desconocidas(donde: str, d: dict, validas: tuple[str, ...]) -> None:
    for clave in d:
        if clave not in validas:
            raise ModeloNoValido(f"{donde}: clave desconocida «{clave}»")


def _clave_foranea(donde: str, valor) -> tuple[str, str | None, str | None]:
    """Una clave foránea: el nombre de su dimensión o un mapa con «dimension» y, si puede ser
    nula por diseño (un rol de fecha que aún no ha ocurrido), «opcional: true» y su «motivo»; hacia
    una SCD2, «fecha»: la columna del hecho con la que se elige la versión. Devuelve la dimensión,
    el motivo (None si no es opcional) y la columna de fecha (o None)."""
    if isinstance(valor, str) and valor:
        return valor, None, None
    if not isinstance(valor, dict):
        raise ModeloNoValido(
            f"{donde}: el nombre de su dimensión, o un mapa con «dimension» (y, si puede ser "
            "nula, «opcional: true» y «motivo»; hacia una SCD2, «fecha»)"
        )
    _sin_desconocidas(donde, valor, ("dimension", "opcional", "motivo", "fecha"))
    dim = valor.get("dimension")
    if not dim or not isinstance(dim, str):
        raise ModeloNoValido(f"{donde}: falta «dimension» (el nombre de su dimensión)")
    opcional = valor.get("opcional", False)
    if not isinstance(opcional, bool):
        raise ModeloNoValido(f"{donde}.opcional: true o false")
    motivo = _motivo(donde, valor)
    if opcional and not motivo:
        raise ModeloNoValido(
            f"{donde}: con «opcional: true» falta «motivo» (por qué puede faltar, p. ej. lo que "
            "aún no ha terminado no tiene fecha de fin)"
        )
    if motivo and not opcional:
        raise ModeloNoValido(f"{donde}: «motivo» solo va con «opcional: true»")
    fecha = valor.get("fecha")
    if fecha is not None and (not isinstance(fecha, str) or not fecha):
        raise ModeloNoValido(f"{donde}.fecha: el nombre de una columna del hecho")
    return dim, motivo, fecha


def _motivo(donde: str, d: dict) -> str | None:
    motivo = d.get("motivo")
    if motivo is not None and (not isinstance(motivo, str) or not motivo.strip()):
        raise ModeloNoValido(f"{donde}.motivo: un texto que explique por qué")
    return motivo.strip() if motivo else None


def _dimension(nombre: str, d, contrato: dict) -> Dimension:
    if not isinstance(d, dict):
        raise ModeloNoValido(f"{nombre}: falta «clave_sustituta»")
    _sin_desconocidas(
        nombre, d, ("clave_sustituta", "clave_natural", "scd2", "miembro_desconocido", "motivo")
    )
    esquema, tabla = _tabla(nombre)
    scd2 = None
    if d.get("scd2") is not None:
        s = d["scd2"]
        donde = f"{tabla}.scd2"
        if not isinstance(s, dict):
            raise ModeloNoValido(f"{donde}: falta «clave_natural»")
        _sin_desconocidas(donde, s, ("clave_natural", "desde", "hasta", "origen"))
        if "clave_natural" not in s:
            raise ModeloNoValido(f"{donde}: falta «clave_natural»")
        origen = _texto(donde, s, "origen")
        if origen not in contrato:
            raise ModeloNoValido(f"{donde}: «{origen}» no es una tabla del contrato del L3")
        scd2 = Scd2(
            _columnas(f"{donde}.clave_natural", s["clave_natural"]),
            _texto(donde, s, "desde"),
            _texto(donde, s, "hasta"),
            origen,
        )
    clave_natural = None
    if d.get("clave_natural") is not None:
        if scd2:
            raise ModeloNoValido(
                f"{tabla}: en una SCD2, la clave natural va en su bloque scd2 (scd2.clave_natural)"
            )
        clave_natural = _columnas(f"{tabla}.clave_natural", d["clave_natural"])
    miembro = d.get("miembro_desconocido", True)
    if not isinstance(miembro, bool):
        raise ModeloNoValido(f"{tabla}.miembro_desconocido: true o false")
    motivo = _motivo(tabla, d)
    if not miembro and not motivo:
        raise ModeloNoValido(
            f"{tabla}: con «miembro_desconocido: false» falta «motivo» (por qué no lo necesita, "
            "p. ej. un calendario generado completo)"
        )
    if motivo and miembro:
        raise ModeloNoValido(f"{tabla}: «motivo» solo va con «miembro_desconocido: false»")
    return Dimension(
        tabla, esquema, _texto(tabla, d, "clave_sustituta"), scd2, miembro, clave_natural
    )


def _tabla(nombre) -> tuple[str, str]:
    if not isinstance(nombre, str) or not nombre or nombre.count(".") > 1:
        raise ModeloNoValido(f"«{nombre}»: el nombre de una tabla (tabla o esquema.tabla)")
    esquema, _, tabla = nombre.rpartition(".")
    return esquema or ESQUEMA_POR_OMISION, tabla


def _contrato(ruta: Path) -> dict:
    if not ruta.is_file():
        raise ModeloNoValido(
            f"no encuentro el contrato del L3 en {ruta}: indica su ruta en «contrato» o el kit "
            "del L3 con L3_KIT (por omisión, ../l03-kit)"
        )
    try:
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ModeloNoValido(f"{ruta.name}: no es YAML válido ({exc.__class__.__name__})") from None
    tablas = datos.get("tablas") if isinstance(datos, dict) else None
    if not isinstance(tablas, dict) or not tablas:
        raise ModeloNoValido(f"{ruta.name}: falta «tablas» (¿es el contrato del L3?)")
    return {n: d if isinstance(d, dict) else {} for n, d in tablas.items()}


def modelo_desde_yaml(ruta: Path) -> Modelo:
    """Lee y valida modelo.yml; ModeloNoValido explica el primer problema que encuentra. Sin
    «contrato», el del kit del L3 (L3_KIT/contrato.yml)."""
    ruta = Path(ruta)
    try:
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except OSError:
        raise ModeloNoValido(f"no encuentro {ruta}") from None
    except yaml.YAMLError as exc:
        raise ModeloNoValido(f"{ruta.name}: no es YAML válido ({exc.__class__.__name__})") from None
    if not isinstance(datos, dict):
        raise ModeloNoValido(f"{ruta.name}: falta «version», «hechos» y «dimensiones»")
    if datos.get("version") != 1:
        raise ModeloNoValido(f"{ruta.name}: «version» debe ser 1")
    _sin_desconocidas(ruta.name, datos, ("version", "contrato", "hechos", "dimensiones"))
    hechos_yml = _mapa(ruta.name, datos.get("hechos"), "hechos")
    dimensiones_yml = _mapa(ruta.name, datos.get("dimensiones"), "dimensiones")
    if not hechos_yml and not dimensiones_yml:
        raise ModeloNoValido(f"{ruta.name}: falta «hechos» o «dimensiones»")
    if datos.get("contrato"):
        contrato_ruta = ruta.parent / str(datos["contrato"])
    else:
        contrato_ruta = Path(os.environ.get("L3_KIT", "../l03-kit")) / "contrato.yml"
    contrato = _contrato(contrato_ruta)

    dimensiones = [_dimension(n, d, contrato) for n, d in dimensiones_yml.items()]
    por_nombre = {d.nombre: d for d in dimensiones}
    nombres = set(por_nombre) | set(dimensiones_yml)

    hechos = []
    for nombre, d in hechos_yml.items():
        esquema, tabla = _tabla(nombre)
        if not isinstance(d, dict) or "grano" not in d:
            raise ModeloNoValido(f"{tabla}: falta «grano»")
        _sin_desconocidas(tabla, d, ("grano", "claves_foraneas"))
        foraneas_yml = _mapa(tabla, d.get("claves_foraneas"), "claves_foraneas")
        foraneas, opcionales, fechas = {}, {}, {}
        for columna, valor in foraneas_yml.items():
            dim, motivo, fecha = _clave_foranea(f"{tabla}.{columna}", valor)
            if dim not in nombres:
                raise ModeloNoValido(
                    f"{tabla}.{columna}: la dimensión «{dim}» no está en «dimensiones»"
                )
            foraneas[columna] = _tabla(dim)[1]
            if motivo:
                opcionales[columna] = motivo
            if fecha:
                if not por_nombre[foraneas[columna]].scd2:
                    raise ModeloNoValido(
                        f"{tabla}.{columna}: «fecha» solo va hacia una dimensión SCD2 (con su "
                        "bloque scd2): es la columna del hecho con la que se elige su versión"
                    )
                fechas[columna] = fecha
        hechos.append(
            Hecho(
                tabla,
                esquema,
                _columnas(f"{tabla}.grano", d["grano"]),
                foraneas,
                opcionales,
                fechas,
            )
        )

    personales = {
        t: tuple(d.get("personales") or ()) for t, d in contrato.items() if d.get("personales")
    }
    return Modelo(
        tuple(hechos),
        tuple(dimensiones),
        contrato,
        personales,
        estrategias_de_snapshots(ruta.parent),
    )


_SOURCE_RAW = re.compile(r"""source\(\s*['"]raw['"]\s*,\s*['"]([^'"]+)['"]\s*\)""")
_REF = re.compile(r"""ref\(\s*['"]([^'"]+)['"]\s*\)""")


def estrategias_de_snapshots(raiz: Path) -> dict[str, frozenset[str]]:
    """Tabla de raw → estrategias («timestamp», «check») de los snapshots que la leen: los de
    snapshots/*.yml, por la tabla de raw que lee su modelo de staging (o su source). Lo que no se
    puede leer se ignora: entonces el aviso de la estrategia es condicional."""
    leen = {}
    for f in sorted((raiz / "models").rglob("*.sql")) if (raiz / "models").is_dir() else ():
        try:
            m = _SOURCE_RAW.search(f.read_text(encoding="utf-8"))
        except OSError:
            continue
        if m:
            leen[f.stem] = m.group(1)
    res: dict[str, set[str]] = {}
    for f in sorted((raiz / "snapshots").glob("*.y*ml")) if (raiz / "snapshots").is_dir() else ():
        try:
            datos = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        for s in (datos.get("snapshots") or []) if isinstance(datos, dict) else ():
            if not isinstance(s, dict) or not isinstance(s.get("config"), dict):
                continue
            estrategia, relacion = s["config"].get("strategy"), str(s.get("relation") or "")
            fuente = _SOURCE_RAW.search(relacion)
            ref = _REF.search(relacion)
            tabla = fuente.group(1) if fuente else leen.get(ref.group(1)) if ref else None
            if tabla and isinstance(estrategia, str):
                res.setdefault(tabla, set()).add(estrategia)
    return {t: frozenset(e) for t, e in res.items()}


# --- Comprobaciones contra la base ---


def _id(*partes: str):
    from psycopg import sql

    return sql.Identifier(*partes)


def _columnas_de(con, esquema: str, tabla: str) -> list[str] | None:
    filas = con.execute(
        "select a.attname from pg_attribute a join pg_class c on c.oid = a.attrelid "
        "join pg_namespace n on n.oid = c.relnamespace where n.nspname = %s and c.relname = %s "
        "and a.attnum > 0 and not a.attisdropped order by a.attnum",
        (esquema, tabla),
    ).fetchall()
    return [f[0] for f in filas] or None


def _existe(con, esquema, tabla, columnas, objeto) -> list[Hallazgo]:
    """Errores si falta la tabla o alguna columna (nada más se comprueba de ella)."""
    hay = _columnas_de(con, esquema, tabla)
    if hay is None:
        return [
            Hallazgo("error", objeto, f"no existe {esquema}.{tabla} (¿has ejecutado make dbt?)")
        ]
    return [
        Hallazgo("error", f"{tabla}.{c}", f"no existe la columna en {esquema}.{tabla}")
        for c in columnas
        if c not in hay
    ]


def _uno(con, consulta, params=()):
    return con.execute(consulta, params).fetchone()[0]


def _tipo(con, esquema: str, tabla: str, columna: str) -> str | None:
    """El tipo de la columna, o None si la tabla o la columna no existen."""
    fila = con.execute(
        "select format_type(a.atttypid, a.atttypmod) from pg_attribute a join pg_class c "
        "on c.oid = a.attrelid join pg_namespace n on n.oid = c.relnamespace where "
        "n.nspname = %s and c.relname = %s and a.attname = %s and not a.attisdropped",
        (esquema, tabla, columna),
    ).fetchone()
    return fila[0] if fila else None


def _no_entera(con, esquema, tabla, columna, objeto, que) -> Hallazgo | None:
    """Un error si la columna no es entera: compararla con −1 no tendría sentido (y fallaría)."""
    tipo = _tipo(con, esquema, tabla, columna)
    if tipo in ENTEROS:
        return None
    return Hallazgo(
        "error",
        objeto,
        f"{que} es de tipo {tipo}: ha de ser entera, como −1 (un hash en texto, como el de md5, "
        "se puede convertir a bigint)",
    )


def _no_especial(columna):
    from psycopg import sql

    return sql.SQL("{} not in (-1, -2)").format(columna)


def comprobar_hecho(con, h: Hecho, dimensiones: dict[str, Dimension]) -> list[Hallazgo]:
    from psycopg import sql

    columnas = [*h.grano, *h.claves_foraneas, *h.fechas.values()]
    faltan = _existe(con, h.esquema, h.nombre, list(dict.fromkeys(columnas)), h.nombre)
    if faltan:
        return faltan
    hallazgos = []
    tabla = _id(h.esquema, h.nombre)
    grano = sql.SQL(", ").join(_id(c) for c in h.grano)
    repetidos = _uno(
        con,
        sql.SQL("select count(*) from (select 1 from {} group by {} having count(*) > 1) r").format(
            tabla, grano
        ),
    )
    texto = ", ".join(h.grano)
    alguno_nulo = sql.SQL(" or ").join(sql.SQL("{} is null").format(_id(c)) for c in h.grano)
    nulos = _uno(con, sql.SQL("select count(*) from {} where {}").format(tabla, alguno_nulo))
    if nulos:
        hallazgos.append(
            Hallazgo(
                "error", h.nombre, f"{nulos} filas con alguna columna del grano ({texto}) nula"
            )
        )
    if repetidos:
        hallazgos.append(
            Hallazgo(
                "error",
                h.nombre,
                f"el grano ({texto}) se repite: {repetidos} combinaciones con más "
                "de una fila (¿falta una columna en el grano o un join multiplica filas?)",
            )
        )
    elif not nulos:
        hallazgos.append(Hallazgo("ok", h.nombre, f"grano único ({texto})"))
    for columna, nombre_dim in h.claves_foraneas.items():
        d = dimensiones[nombre_dim]
        de_la_dimension = _columnas_de(con, d.esquema, d.nombre)
        if de_la_dimension is None or d.clave_sustituta not in de_la_dimension:
            continue  # su dimensión ya da el error (no existe ella o su clave sustituta)
        objeto = f"{h.nombre}.{columna}"
        mala = _no_entera(con, h.esquema, h.nombre, columna, objeto, "la clave foránea")
        if mala or _tipo(con, d.esquema, d.nombre, d.clave_sustituta) not in ENTEROS:
            hallazgos += [mala] if mala else []  # la de la dimensión ya da su error
            continue
        hallazgos += _clave_foranea_en_base(con, h, tabla, columna, objeto, d)
    return hallazgos


def _clave_foranea_en_base(con, h: Hecho, tabla, columna, objeto, d: Dimension) -> list:
    from psycopg import sql

    hallazgos = []
    col = _id(columna)
    nulos = _uno(con, sql.SQL("select count(*) from {} where {} is null").format(tabla, col))
    huerfanos = _uno(
        con,
        sql.SQL(
            "select count(*) from {} f where f.{} is not null and f.{} <> -1 and not exists "
            "(select 1 from {} d where d.{} = f.{})"
        ).format(tabla, col, col, _id(d.esquema, d.nombre), _id(d.clave_sustituta), col),
    )
    menos_uno = (
        0
        if d.miembro_desconocido
        else _uno(con, sql.SQL("select count(*) from {} where {} = -1").format(tabla, col))
    )
    opcional = columna in h.opcionales
    if nulos and not opcional:
        hallazgos.append(
            Hallazgo(
                "error",
                objeto,
                f"{nulos} filas con la clave nula: el desconocido es −1, con su fila en "
                f"{d.nombre}; si puede faltar por diseño (una fecha que aún no ha ocurrido), "
                "decláralo con «opcional: true» y su «motivo»",
            )
        )
    if huerfanos:
        hallazgos.append(
            Hallazgo(
                "error",
                objeto,
                f"{huerfanos} filas sin su fila en {d.nombre}.{d.clave_sustituta}"
                " (huérfanas; lo que no casa va al desconocido, −1)",
            )
        )
    if menos_uno:
        hallazgos.append(
            Hallazgo(
                "error",
                objeto,
                f"{menos_uno} filas con −1, pero {d.nombre} no tiene miembro desconocido "
                "(«miembro_desconocido: false»): si la clave puede faltar, déjala nula con "
                "«opcional: true» y su «motivo»",
            )
        )
    if (opcional or not nulos) and not huerfanos and not menos_uno:
        admite = f" (admite nulos: {h.opcionales[columna]})" if opcional else ""
        hallazgos.append(Hallazgo("ok", objeto, f"sin huérfanos en {d.nombre}{admite}"))
    if columna in h.fechas and {d.scd2.desde, d.scd2.hasta} <= set(
        _columnas_de(con, d.esquema, d.nombre) or ()
    ):  # si le falta desde o hasta, la dimensión ya da el error
        hallazgos.append(_version_en_su_fecha(con, tabla, columna, h.fechas[columna], objeto, d))
    if d.miembro_desconocido:
        aviso = _aviso_desconocidos(con, tabla, columna, objeto, d)
        if aviso:
            hallazgos.append(aviso)
    return hallazgos


def _version_en_su_fecha(con, tabla, columna, fecha, objeto, d: Dimension) -> Hallazgo:
    """Las filas del hecho que apuntan a una versión de la SCD2 que no estaba vigente en su
    fecha (fuera de [desde, hasta)): el síntoma de unir por la versión actual."""
    from psycopg import sql

    s = d.scd2
    fuera = _uno(
        con,
        sql.SQL(
            "select count(*) from {t} f join {d} v on v.{sk} = f.{col} where f.{col} not in "
            "(-1, -2) and f.{fecha} is not null and (f.{fecha} < v.{desde} or "
            "f.{fecha} >= coalesce(v.{hasta}, 'infinity'))"
        ).format(
            t=tabla,
            d=_id(d.esquema, d.nombre),
            sk=_id(d.clave_sustituta),
            col=_id(columna),
            fecha=_id(fecha),
            desde=_id(s.desde),
            hasta=_id(s.hasta),
        ),
    )
    if fuera:
        return Hallazgo(
            "error",
            objeto,
            f"{fuera} filas apuntan a una versión de {d.nombre} que no estaba vigente en su "
            f"{fecha}: ¿unes por la versión actual en vez de por el intervalo "
            f"[{s.desde}, {s.hasta})?",
        )
    return Hallazgo(
        "ok", objeto, f"cada fila apunta a la versión de {d.nombre} vigente en su {fecha}"
    )


# Si más de esta fracción de las filas de un hecho va al desconocido (−1) de una dimensión, avisa:
# no es un error (puede haber hechos sin su miembro), pero suele ser una unión que no casa.
UMBRAL_DESCONOCIDO = 0.05


def _aviso_desconocidos(con, tabla, columna, objeto, d: Dimension) -> Hallazgo | None:
    """Un aviso de forma, sin cifras salvo la proporción: muchas filas del hecho en el −1 (de las
    que tienen la clave: en una opcional, las nulas no cuentan)."""
    from psycopg import sql

    filas, desconocidas = con.execute(
        sql.SQL("select count({c}), count(*) filter (where {c} = -1) from {t}").format(
            c=_id(columna), t=tabla
        )
    ).fetchone()
    if not filas or desconocidas <= UMBRAL_DESCONOCIDO * filas:
        return None
    if d.scd2:
        pista = (
            f"¿empieza la primera versión de cada clave de {d.nombre} después de los hechos más "
            "antiguos? Un snapshot abre la primera versión de cada clave en su última "
            "modificación (o en su primera carga), y un hecho anterior no casa con ninguna: haz "
            "que la primera versión cubra los hechos más antiguos. Si no es eso, revisa la unión "
            "(tipos de la clave, la fecha del hecho)"
        )
    else:
        pista = "revisa la unión con la dimensión (los tipos de la clave natural, sus valores)"
    pista += (
        ". Si la clave falta por diseño (una fecha que aún no ha ocurrido), no es un desconocido: "
        "déjala nula con «opcional: true» y su «motivo», o usa −2 («no aplica») si la dimensión "
        "tiene esa fila"
    )
    return Hallazgo(
        "aviso",
        objeto,
        f"el {round(100 * desconocidas / filas)} % de las filas van al desconocido (−1) de "
        f"{d.nombre}: {pista}",
    )


def vigente_sql(hasta):
    """La condición de versión vigente: hasta nulo o del año 9999. Por el año, no comparando con
    '9999-12-31': con timestamptz, esa comparación depende de la zona horaria de la sesión
    (comprobar() además la fija en UTC)."""
    from psycopg import sql

    return sql.SQL("({} is null or extract(year from {}) >= 9999)").format(hasta, hasta)


def comprobar_dimension(con, d: Dimension, modelo: Modelo) -> list[Hallazgo]:
    from psycopg import sql

    columnas = [d.clave_sustituta, *(d.clave_natural or ())]
    if d.scd2:
        columnas += [*d.scd2.clave_natural, d.scd2.desde, d.scd2.hasta]
    faltan = _existe(con, d.esquema, d.nombre, list(dict.fromkeys(columnas)), d.nombre)
    if faltan:
        return faltan
    objeto_sk = f"{d.nombre}.{d.clave_sustituta}"
    mala = _no_entera(con, d.esquema, d.nombre, d.clave_sustituta, objeto_sk, "la clave sustituta")
    if mala:
        return [mala]
    hallazgos = []
    tabla, sk = _id(d.esquema, d.nombre), _id(d.clave_sustituta)
    desconocidos = _uno(con, sql.SQL("select count(*) from {} where {} = -1").format(tabla, sk))
    if d.miembro_desconocido and desconocidos != 1:
        que = "falta el miembro desconocido" if not desconocidos else "el desconocido se repite"
        hallazgos.append(
            Hallazgo("error", d.nombre, f"{que} (una fila con {d.clave_sustituta} = −1)")
        )
    if not d.miembro_desconocido and desconocidos:
        hallazgos.append(
            Hallazgo(
                "error",
                d.nombre,
                f"tiene una fila con {d.clave_sustituta} = −1, pero declaras "
                "«miembro_desconocido: false»",
            )
        )
    repetidas = _uno(
        con,
        sql.SQL("select count(*) from (select 1 from {} group by {} having count(*) > 1) r").format(
            tabla, sk
        ),
    )
    if repetidas:
        hallazgos.append(
            Hallazgo("error", objeto_sk, f"la clave sustituta se repite en {repetidas} valores")
        )
    bien = not repetidas and desconocidos == (1 if d.miembro_desconocido else 0)
    if not d.scd2:
        if d.clave_natural:
            nk = sql.SQL(", ").join(_id(c) for c in d.clave_natural)
            nk_repetidas = _uno(
                con,
                sql.SQL(
                    "select count(*) from (select 1 from {} where {} group by {} "
                    "having count(*) > 1) r"
                ).format(tabla, _no_especial(sk), nk),
            )
            if nk_repetidas:
                bien = False
                hallazgos.append(
                    Hallazgo(
                        "error",
                        d.nombre,
                        f"la clave natural ({', '.join(d.clave_natural)}) se repite en "
                        f"{nk_repetidas} valores: sin historia, una fila por clave (¿guarda "
                        "historia y le falta su bloque scd2, o un join multiplica filas?)",
                    )
                )
        if bien:
            que = ["miembro desconocido" if d.miembro_desconocido else "sin miembro desconocido"]
            que += ["clave sustituta única"] + (["clave natural única"] if d.clave_natural else [])
            hallazgos.append(Hallazgo("ok", d.nombre, f"{', '.join(que[:-1])} y {que[-1]}"))
        return hallazgos
    return hallazgos + _comprobar_scd2(con, d, tabla, sk, bien, modelo)


def _comprobar_scd2(con, d: Dimension, tabla, sk, bien: bool, modelo: Modelo) -> list[Hallazgo]:
    from psycopg import sql

    hallazgos = []
    s = d.scd2
    nk = sql.SQL(", ").join(_id(c) for c in s.clave_natural)
    nk_igual = sql.SQL(" and ").join(
        sql.SQL("a.{} = b.{}").format(_id(c), _id(c)) for c in s.clave_natural
    )
    desde, hasta = _id(s.desde), _id(s.hasta)
    vigente = vigente_sql(hasta)
    real = _no_especial(sk)
    claves = ", ".join(s.clave_natural)
    varias, ninguna = con.execute(
        sql.SQL(
            "select count(*) filter (where n > 1), count(*) filter (where n = 0) from "
            "(select count(*) filter (where {}) as n from {} where {} group by {}) r"
        ).format(vigente, tabla, real, nk)
    ).fetchone()
    sin_desde = _uno(
        con, sql.SQL("select count(*) from {} where {} and {} is null").format(tabla, real, desde)
    )
    vacios = _uno(
        con,
        sql.SQL("select count(*) from {} where {} and {} >= coalesce({}, 'infinity')").format(
            tabla, real, desde, hasta
        ),
    )
    if sin_desde:
        hallazgos.append(
            Hallazgo(
                "error",
                f"{d.nombre}.{s.desde}",
                f"{sin_desde} versiones sin inicio: cada versión tiene su {s.desde}",
            )
        )
    if vacios:
        hallazgos.append(
            Hallazgo(
                "error",
                f"{d.nombre}.{s.desde}",
                f"{vacios} versiones con {s.desde} igual o posterior a {s.hasta}: en un intervalo "
                f"[{s.desde}, {s.hasta}) vacío o invertido no cae ningún hecho",
            )
        )
    if varias:
        hallazgos.append(
            Hallazgo(
                "error",
                d.nombre,
                f"{varias} claves naturales ({claves}) con más de una versión "
                f"vigente ({s.hasta} nulo o del año 9999)",
            )
        )
    if ninguna:
        hallazgos.append(
            Hallazgo(
                "error",
                d.nombre,
                f"{ninguna} claves naturales ({claves}) sin ninguna versión vigente ({s.hasta} "
                "nulo o del año 9999): cada clave tiene exactamente una (¿se cierra también la "
                "última versión, o un borrado en el origen la ha cerrado?)",
            )
        )
    solapes = _uno(
        con,
        sql.SQL(
            "select count(distinct ({nk_a})) from {t} a join {t} b on {igual} and a.{sk} <> b.{sk} "
            "where a.{sk} not in (-1, -2) and b.{sk} not in (-1, -2) "
            "and a.{desde} < coalesce(b.{hasta}, 'infinity') "
            "and b.{desde} < coalesce(a.{hasta}, 'infinity')"
        ).format(
            nk_a=sql.SQL(", ").join(sql.SQL("a.{}").format(_id(c)) for c in s.clave_natural),
            t=tabla,
            igual=nk_igual,
            sk=sk,
            desde=desde,
            hasta=hasta,
        ),
    )
    if solapes:
        hallazgos.append(
            Hallazgo(
                "error",
                d.nombre,
                f"{solapes} claves naturales ({claves}) con intervalos [{s.desde}, {s.hasta}) que"
                " se solapan: los intervalos de una misma clave no deben solaparse",
            )
        )
    huecos = _uno(
        con,
        sql.SQL(
            "select count(distinct ({nk})) from (select {nk}, {hasta} as hasta, lead({desde}) "
            "over (partition by {nk} order by {desde}) as siguiente from {t} where {real}) r "
            "where siguiente > hasta"
        ).format(nk=nk, hasta=hasta, desde=desde, t=tabla, real=real),
    )
    if huecos:
        hallazgos.append(
            Hallazgo(
                "aviso",
                d.nombre,
                f"{huecos} claves naturales ({claves}) con huecos entre versiones (una empieza "
                "después de que acabe la anterior): un hecho de entre medias no casa con ninguna "
                "e iría al −1",
            )
        )
    if bien and not (varias or ninguna or solapes or sin_desde or vacios):
        con_desconocido = ", con el desconocido" if d.miembro_desconocido else ""
        hallazgos.append(
            Hallazgo(
                "ok",
                d.nombre,
                "SCD2: exactamente una versión vigente por clave natural, intervalos no vacíos y "
                f"sin solapes{con_desconocido}",
            )
        )
    aviso = _aviso_estrategia(d, modelo)
    return hallazgos + ([aviso] if aviso else [])


def _aviso_estrategia(d: Dimension, modelo: Modelo) -> Hallazgo | None:
    """Sin columna de última modificación en raw, un snapshot con strategy: timestamp no ve los
    cambios. Si los snapshots del kit dicen la estrategia de esa tabla, solo avisa con timestamp;
    si no se sabe, lo dice como condición."""
    s = d.scd2
    if modelo.contrato.get(s.origen, {}).get("incremental"):
        return None
    estrategias = modelo.estrategias.get(s.origen, frozenset())
    if estrategias and "timestamp" not in estrategias:
        return None
    sin = (
        f"raw.{s.origen} no tiene columna de última modificación («incremental» en el contrato "
        "del L3)"
    )
    if "timestamp" in estrategias:
        que = f"su snapshot usa strategy: timestamp, pero {sin}: no puede detectar sus cambios"
    else:
        que = f"si su snapshot usa strategy: timestamp, no detectará sus cambios: {sin}"
    return Hallazgo(
        "aviso",
        d.nombre,
        f"su historia sale de raw.{s.origen}; {que}. Usa strategy: check con check_cols (las "
        "columnas cuyo cambio abre una versión)",
    )


def _relaciones(con) -> list[tuple[str, str]]:
    """Tablas y vistas que ha construido tu modelo (todo lo de fuera de raw y meta)."""
    return con.execute(
        "select n.nspname, c.relname from pg_class c join pg_namespace n on n.oid = c.relnamespace"
        " where c.relkind in ('r', 'v', 'm', 'p') and n.nspname <> all(%s) "
        "and n.nspname not like 'pg\\_%%' order by 1, 2",
        (list(FUERA_DEL_MODELO),),
    ).fetchall()


# Un dato personal «identificativo» (casi un valor por persona: un correo, un nombre) se busca
# también por sus valores en cualquier columna, con otro nombre y sin la clave: hace falta que
# al menos MIN_COINCIDENCIAS valores distintos de la columna, y la mitad, estén en raw. Uno con
# pocos valores (un distrito, una fecha) no: coincidiría con columnas que no son el dato.
MIN_DISTINTOS = 20
MIN_COINCIDENCIAS = 10


def _identificativos(con, modelo: Modelo) -> tuple[set, set, list[Hallazgo]]:
    """Los personales identificativos, los que no se pueden comprobar (no están en raw o no se
    leen) y sus errores, con tabla y columna."""
    import psycopg
    from psycopg import sql

    identificativos, ausentes, hallazgos = set(), set(), []
    for tabla, personales in modelo.personales.items():
        columnas = _columnas_de(con, "raw", tabla)
        for p in personales:
            if columnas is None or p not in columnas:
                donde = f"raw.{tabla}" if columnas is None else f"la columna en raw.{tabla}"
                ausentes.add((tabla, p))
                hallazgos.append(
                    Hallazgo(
                        "error",
                        f"{tabla}.{p}",
                        f"dato personal del contrato sin comprobar: no existe {donde} "
                        "(¿has cargado con el kit del L3?)",
                    )
                )
                continue
            try:
                distintos, filas = con.execute(
                    sql.SQL(
                        "select count(distinct {p}::text), count({p}) from {t} "
                        "where nullif({p}::text, '') is not null"
                    ).format(p=_id(p), t=_id("raw", tabla))
                ).fetchone()
            except psycopg.Error as exc:
                ausentes.add((tabla, p))
                hallazgos.append(
                    Hallazgo(
                        "error",
                        f"{tabla}.{p}",
                        f"dato personal sin comprobar: no se pudo leer raw.{tabla}.{p} "
                        f"({type(exc).__name__})",
                    )
                )
                continue
            if distintos >= MIN_DISTINTOS and distintos >= 0.9 * filas:
                identificativos.add((tabla, p))
    return identificativos, ausentes, hallazgos


def _por_valores(con, esquema, relacion, c, tabla, p) -> bool:
    from psycopg import sql

    distintos, en_raw = con.execute(
        sql.SQL(
            "with v as (select distinct m.{c}::text as v from {m} m "
            "where nullif(m.{c}::text, '') is not null) "
            "select count(*), count(*) filter (where v in (select r.{p}::text from {r} r)) from v"
        ).format(c=_id(c), m=_id(esquema, relacion), p=_id(p), r=_id("raw", tabla))
    ).fetchone()
    return en_raw >= MIN_COINCIDENCIAS and en_raw >= 0.5 * distintos


def _personales_en(
    con,
    esquema,
    relacion,
    columnas,
    modelo: Modelo,
    identificativos=frozenset(),
    ausentes=frozenset(),
) -> list[Hallazgo]:
    from psycopg import sql

    hallazgos = []
    for tabla, personales in modelo.personales.items():
        clave = tuple(modelo.contrato[tabla].get("clave") or ())
        con_clave = bool(clave) and set(clave) <= set(columnas)
        for p in personales:
            if (tabla, p) in ausentes:
                continue
            for c in columnas:
                if c != p and not (con_clave and c not in clave):
                    if (tabla, p) in identificativos and _por_valores(
                        con, esquema, relacion, c, tabla, p
                    ):
                        hallazgos.append(_en_claro(esquema, relacion, c, tabla, p))
                    continue
                iguales = [(c, p)] if c == p else [*((k, k) for k in clave), (c, p)]
                union = sql.SQL(" and ").join(
                    sql.SQL("m.{}::text = r.{}::text").format(_id(a), _id(b)) for a, b in iguales
                )
                en_claro = _uno(
                    con,
                    sql.SQL(
                        "select exists (select 1 from {} m join {} r on {} "
                        "where nullif(r.{}::text, '') is not null)"
                    ).format(_id(esquema, relacion), _id("raw", tabla), union, _id(p)),
                )
                if en_claro or (
                    (tabla, p) in identificativos
                    and _por_valores(con, esquema, relacion, c, tabla, p)
                ):
                    hallazgos.append(_en_claro(esquema, relacion, c, tabla, p))
    return hallazgos


def _en_claro(esquema, relacion, c, tabla, p) -> Hallazgo:
    return Hallazgo(
        "error",
        f"{esquema}.{relacion}.{c}",
        f"dato personal de raw.{tabla}.{p} en claro fuera de raw: "
        "seudonimízalo en staging con seudonimo() o no lo uses",
    )


def comprobar_personales(con, modelo: Modelo) -> list[Hallazgo]:
    """Una columna fuera de raw está «en claro» si sus valores son los de una columna personal
    de raw: la del mismo nombre con algún valor igual; cualquiera que, en la misma fila de raw
    (unida por su clave, si la relación la conserva con el mismo nombre), tenga su mismo valor;
    o, si el dato es identificativo (casi un valor por persona), cualquiera con muchos de sus
    valores. Es una heurística: un dato transformado (en mayúsculas, recortado, concatenado) o
    uno con pocos valores, renombrado y sin la clave, no se detecta."""
    import psycopg

    identificativos, ausentes, hallazgos = _identificativos(con, modelo)
    for esquema, relacion in _relaciones(con):
        columnas = _columnas_de(con, esquema, relacion) or []
        try:
            hallazgos += _personales_en(
                con, esquema, relacion, columnas, modelo, identificativos, ausentes
            )
        except psycopg.Error as exc:
            hallazgos.append(
                Hallazgo(
                    "error",
                    f"{esquema}.{relacion}",
                    f"no se pudo comprobar ({type(exc).__name__}):"
                    " ¿falta la sal? (make comprobar la pone en la conexión)",
                )
            )
    if not hallazgos and modelo.personales:
        n = sum(len(p) for p in modelo.personales.values())
        hallazgos.append(
            Hallazgo("ok", "personales", f"{n} columnas personales, ninguna en claro fuera de raw")
        )
    return hallazgos


def comprobar(con, modelo: Modelo) -> list[Hallazgo]:
    con.execute("set time zone 'UTC'")  # fechas de validez sin depender de la zona de la sesión
    dimensiones = {d.nombre: d for d in modelo.dimensiones}
    hallazgos = []
    for d in modelo.dimensiones:
        hallazgos += comprobar_dimension(con, d, modelo)
    for h in modelo.hechos:
        hallazgos += comprobar_hecho(con, h, dimensiones)
    return hallazgos + comprobar_personales(con, modelo)


def conninfo() -> str:
    """Conexión a la base «proyecto» del kit del L3 (las variables de su .env). La sal de los
    seudónimos llega, si hace falta, por PGOPTIONS (make comprobar la pone)."""
    import psycopg

    if not os.environ.get("PROYECTO_CLAVE"):
        raise ModeloNoValido(
            "falta la variable PROYECTO_CLAVE: está en el .env del kit del L3; ejecuta "
            "make comprobar, que lo lee de L3_KIT (por omisión, ../l03-kit)"
        )
    return psycopg.conninfo.make_conninfo(
        host=os.environ.get("PROYECTO_HOST", "127.0.0.1"),
        port=os.environ.get("PROYECTO_PUERTO", "5440"),
        user=os.environ.get("PROYECTO_USUARIO", "proyecto"),
        password=os.environ["PROYECTO_CLAVE"],
        dbname=os.environ.get("PROYECTO_BASE", "proyecto"),
        connect_timeout=10,
    )


def main(argv: list[str] | None = None) -> int:
    import psycopg

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--modelo", type=Path, default=Path("modelo.yml"))
    args = ap.parse_args(argv)
    try:
        modelo = modelo_desde_yaml(args.modelo)
        with psycopg.connect(conninfo(), autocommit=True) as con:
            hallazgos = comprobar(con, modelo)
    except ModeloNoValido as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    except psycopg.OperationalError as exc:
        print(
            f"ERROR no se pudo conectar a la base ({type(exc).__name__}): ¿está levantada "
            "(make base en el kit del L3) y es correcto su .env (L3_KIT)?",
            file=sys.stderr,
        )
        return 1
    except psycopg.Error as exc:  # p. ej., una clave foránea de otro tipo que su dimensión
        primera = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
        print(f"ERROR no se pudo comprobar ({type(exc).__name__}): {primera}", file=sys.stderr)
        return 1
    for h in hallazgos:
        print(h)
    errores = sum(h.nivel == "error" for h in hallazgos)
    if errores:
        print(f"ERROR modelo: {errores} comprobaciones fallan")
        return 1
    print(f"OK modelo: {len(modelo.hechos)} hechos y {len(modelo.dimensiones)} dimensiones")
    return 0


if __name__ == "__main__":
    sys.exit(main())
