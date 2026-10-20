"""Comprobador del contrato de carga de tu proyecto (laboratorio L3).

El contrato (contrato.yml) dice qué tablas debe dejar tu carga en el esquema raw:

    version: 1
    tablas:
      pedido:
        columnas: [pedido_id, cliente, importe, modificado]
        clave: [pedido_id]
        disposicion: merge         # merge, replace o append (forma de escritura de dlt)
        incremental: modificado    # opcional: columna de última modificación
        fichero: pedidos.csv       # opcional: ruta (o lista, o patrón con *) dentro de datos/;
                                   #   sin él, la tabla sale de proyecto_origen
        esquema_origen: public     # opcional: esquema de la tabla en proyecto_origen
        personales: [cliente]      # opcional: columnas con datos personales
        separador: ";"             # opcional (ficheros): «,», «;», tabulador («\\t») o «|»
        codificacion: utf-8        # opcional (ficheros): p. ej. cp1252 para un CSV de Excel

Los nombres de tabla y columna son identificadores de PostgreSQL sin comillas (minúsculas,
dígitos y _), los mismos que deja dlt en raw (`make columnas` enseña cómo quedan tus cabeceras).

Uso (lo hacen `make contrato`, `make columnas` y `make comprobar`):

    python comprobar_carga.py --contrato contrato.yml --solo-contrato
    python comprobar_carga.py --contrato contrato.yml --columnas [FICHERO ...]
    python comprobar_carga.py --contrato contrato.yml --orden "uv run python carga.py"

Con --orden ejecuta tu carga dos veces: comprueba la idempotencia y anota cuántas filas leyó cada
ejecución. Siempre comprueba el esquema (tablas, columnas, claves, linaje y que las tablas las
haya cargado dlt), el registro de meta.carga y que raw coincide con el origen (tus tablas de
proyecto_origen y tus ficheros de datos/). Una línea OK, AVISO, ERROR o INFO por comprobación;
sale con 0 si no hay errores y con 1 si los hay.

En la parte guiada (make l3-comprobar en la plataforma) comprueba el tercer cargador:
--contrato-atlantida arma el contrato desde GET /tablas de la API del profesor (SIM_API_URL y
SIM_API_TOKEN), no exige dlt, no concilia con proyecto_origen y tiene en cuenta que el origen
sigue cambiando entre las dos ejecuciones; --referencia ESQUEMA compara además lo cargado con
otra carga del mismo origen (raw_pms, la de dlt) hasta el corte común de las dos.
"""

from __future__ import annotations

import argparse
import codecs
import csv
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import quote

import psycopg
import yaml
from psycopg import sql

IDENTIFICADOR = re.compile(r"^[a-z_][a-z0-9_]*$")
CLAVES_TABLA = {
    "columnas",
    "clave",
    "disposicion",
    "incremental",
    "fichero",
    "esquema_origen",
    "personales",
    "separador",
    "codificacion",
}
DISPOSICIONES = ("merge", "replace", "append")
SEPARADORES = (",", ";", "\t", "|")
LINAJE = ("_loaded_at", "_origen")
LINAJE_FICHERO = ("_origen", "_fila")  # pueden formar la clave de un fichero sin clave natural
FUERA_DE_LA_HUELLA = {"_loaded_at", "_dlt_load_id", "_dlt_id"}


class ContratoNoValido(ValueError):
    """El contrato no se puede usar; el mensaje dice qué falta o qué está mal."""


class FicheroNoValido(ValueError):
    """Un fichero de datos/ no se puede leer tal como dice el contrato; el mensaje dice por qué."""


@dataclass(frozen=True)
class TablaContrato:
    nombre: str
    columnas: tuple[str, ...]
    clave: tuple[str, ...]
    incremental: str | None
    fichero: str | tuple[str, ...] | None = None
    esquema_origen: str = "public"
    disposicion: str = "merge"
    personales: tuple[str, ...] = ()
    separador: str | None = None
    codificacion: str = "utf-8"

    @property
    def patrones(self) -> tuple[str, ...]:
        """Las rutas (o patrones con *) de sus ficheros dentro de datos/."""
        if self.fichero is None:
            return ()
        return (self.fichero,) if isinstance(self.fichero, str) else tuple(self.fichero)

    @property
    def clave_foto(self) -> tuple[str, ...]:
        """Lo que identifica una fila en raw: la clave y, con append, también el incremental
        (raw guarda varias versiones de cada clave)."""
        if self.disposicion == "append" and self.incremental:
            return (*self.clave, self.incremental)
        return self.clave


@dataclass(frozen=True)
class ContratoCarga:
    tablas: tuple[TablaContrato, ...]


def _identificador(donde: str, valor) -> str:
    if not isinstance(valor, str) or not IDENTIFICADOR.match(valor):
        raise ContratoNoValido(
            f"{donde}: usa minúsculas, dígitos y _ (identificador de PostgreSQL sin comillas)"
        )
    return valor


def _lista(tabla: str, campo: str, valor) -> tuple[str, ...]:
    if not isinstance(valor, list) or not valor:
        raise ContratoNoValido(f"{tabla}: «{campo}» debe ser una lista no vacía")
    return tuple(_identificador(f"{tabla}.{c}", c) for c in valor)


def _una_ruta(tabla: str, valor) -> str:
    ruta = PurePosixPath(str(valor)) if isinstance(valor, str) and valor else None
    if ruta is None or ruta.is_absolute() or ".." in ruta.parts or "\\" in str(valor):
        raise ContratoNoValido(f"{tabla}.fichero: ruta dentro de datos/ (sin .. ni ruta absoluta)")
    return str(ruta)


def _fichero(tabla: str, valor) -> str | tuple[str, ...]:
    if isinstance(valor, list):
        if not valor:
            raise ContratoNoValido(f"{tabla}.fichero: la lista de ficheros está vacía")
        return tuple(_una_ruta(tabla, v) for v in valor)
    return _una_ruta(tabla, valor)


def _tabla(nombre, datos) -> TablaContrato:
    nombre = _identificador(str(nombre), nombre)
    if not isinstance(datos, dict):
        raise ContratoNoValido(f"{nombre}: falta «columnas»")
    for clave in datos:
        if clave not in CLAVES_TABLA:
            raise ContratoNoValido(
                f"{nombre}: clave desconocida «{clave}» (usa {', '.join(sorted(CLAVES_TABLA))})"
            )
    for campo in ("columnas", "clave", "disposicion"):
        if campo not in datos:
            raise ContratoNoValido(f"{nombre}: falta «{campo}»")
    columnas = _lista(nombre, "columnas", datos["columnas"])
    for c in columnas:
        if c in (*LINAJE, "_fila") or c.startswith("_dlt_"):
            raise ContratoNoValido(
                f"{nombre}: {c} es de linaje o de dlt: no va en «columnas» (el comprobador la "
                "mira aparte)"
            )
    if len(set(columnas)) != len(columnas):
        raise ContratoNoValido(f"{nombre}: hay columnas repetidas en «columnas»")
    fichero = _fichero(nombre, datos["fichero"]) if datos.get("fichero") is not None else None
    clave = _lista(nombre, "clave", datos["clave"])
    for c in clave:
        if c not in columnas and not (fichero and c in LINAJE_FICHERO):
            raise ContratoNoValido(f"{nombre}: la clave {c} no está en columnas")
    disposicion = datos["disposicion"]
    if disposicion not in DISPOSICIONES:
        raise ContratoNoValido(f"{nombre}: «disposicion» debe ser merge, replace o append")
    incremental = datos.get("incremental")
    if incremental is not None:
        _identificador(f"{nombre}.{incremental}", incremental)
        if incremental not in columnas:
            raise ContratoNoValido(
                f"{nombre}: la columna incremental {incremental} no está en columnas"
            )
        if disposicion == "replace":
            raise ContratoNoValido(
                f"{nombre}: replace relee la tabla entera y la sustituye; con «incremental» "
                "solo dejaría en raw las filas nuevas (usa merge o append, o quita incremental)"
            )
    personales = ()
    if datos.get("personales") is not None:
        personales = _lista(nombre, "personales", datos["personales"])
        for c in personales:
            if c not in columnas:
                raise ContratoNoValido(f"{nombre}: la columna personal {c} no está en columnas")
    separador = datos.get("separador")
    if separador == "\\t":  # "\t" entre comillas simples en el YAML
        separador = "\t"
    codificacion = datos.get("codificacion", "utf-8")
    if (separador is not None or "codificacion" in datos) and fichero is None:
        raise ContratoNoValido(f"{nombre}: «separador» y «codificacion» solo valen con «fichero»")
    if separador is not None and separador not in SEPARADORES:
        raise ContratoNoValido(f'{nombre}: «separador» debe ser ",", ";", "\\t" o "|"')
    try:
        codecs.lookup(str(codificacion))
    except LookupError:
        raise ContratoNoValido(
            f"{nombre}: codificación desconocida «{codificacion}» (p. ej. utf-8 o cp1252)"
        ) from None
    esquema = _identificador(f"{nombre}.esquema_origen", datos.get("esquema_origen", "public"))
    return TablaContrato(
        nombre,
        columnas,
        clave,
        incremental,
        fichero,
        esquema,
        disposicion,
        personales,
        separador,
        str(codificacion),
    )


def contrato_desde_yaml(ruta: Path) -> ContratoCarga:
    """Lee y valida el contrato; ContratoNoValido explica el primer problema que encuentra."""
    ruta = Path(ruta)
    try:
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ContratoNoValido(
            f"{ruta.name}: no es YAML válido ({exc.__class__.__name__})"
        ) from None
    if not isinstance(datos, dict):
        raise ContratoNoValido(f"{ruta.name}: falta «version» y «tablas»")
    if datos.get("version") != 1:
        raise ContratoNoValido(f"{ruta.name}: «version» debe ser 1")
    for clave in datos:
        if clave not in ("version", "tablas"):
            raise ContratoNoValido(f"{ruta.name}: clave desconocida «{clave}»")
    tablas = datos.get("tablas")
    if not tablas:
        raise ContratoNoValido(f"{ruta.name}: falta «tablas»")
    if not isinstance(tablas, dict):
        raise ContratoNoValido(f"{ruta.name}: «tablas» debe ser un mapa nombre → definición")
    return ContratoCarga(tuple(_tabla(n, d) for n, d in tablas.items()))


# --- Ficheros (los usan carga.py y las comprobaciones) ---


def contrato_desde_api(tablas) -> ContratoCarga:
    """El contrato de las tablas que sirve la API de cambios (el cuerpo de GET /tablas): sus
    columnas y su clave; incremental, updated_at si la tabla la tiene; replace si la clave admite
    nulos (NULL no casa en un upsert) y merge si no."""
    if not isinstance(tablas, list) or not tablas:
        raise ContratoNoValido("la API no devuelve una lista de tablas en /tablas")
    resultado = []
    for t in tablas:
        try:
            nombre = _identificador("tabla de la API", t["tabla"])
            columnas = tuple(_identificador(nombre, c["nombre"]) for c in t["columnas"])
            clave = tuple(_identificador(nombre, c) for c in t["clave"])
            con_nulos = tuple(t.get("clave_con_nulos") or ())
        except (KeyError, TypeError) as exc:
            raise ContratoNoValido(f"/tablas de la API sin el campo {exc}") from None
        incremental = "updated_at" if "updated_at" in columnas else None
        disposicion = "replace" if con_nulos else "merge"
        resultado.append(
            TablaContrato(nombre, columnas, clave, incremental, None, "public", disposicion)
        )
    return ContratoCarga(tuple(resultado))


def contrato_atlantida() -> ContratoCarga:
    """El contrato de Atlántida, leído de GET /tablas de la API del profesor (SIM_API_URL y, si
    está, SIM_API_TOKEN)."""
    url = os.environ.get("SIM_API_URL", "").rstrip("/")
    if not url:
        raise FaltaVariable(
            "SIM_API_URL", "la URL de la API que te da el profesor, en platform/.env"
        )
    token = os.environ.get("SIM_API_TOKEN", "")
    peticion = urllib.request.Request(
        f"{url}/tablas", headers={"Authorization": f"Bearer {token}"} if token else {}
    )
    try:
        with urllib.request.urlopen(peticion, timeout=60) as r:
            cuerpo = json.loads(r.read())
    except urllib.error.HTTPError as exc:
        pista = " (revisa SIM_API_TOKEN)" if exc.code == 401 else ""
        raise ContratoNoValido(
            f"no se pudo leer /tablas de la API: HTTP {exc.code}{pista}"
        ) from None
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise ContratoNoValido(
            f"no se pudo leer /tablas de la API ({type(exc).__name__}): revisa SIM_API_URL"
        ) from None
    return contrato_desde_api(cuerpo)


def normalizar(nombre: str) -> str:
    """El nombre que deja dlt en raw para una cabecera o columna (su convención snake_case)."""
    from dlt.common.normalizers.naming.snake_case import NamingConvention

    return NamingConvention().normalize_identifier(nombre)


def ficheros_de(carpeta: Path, t: TablaContrato) -> list[Path]:
    """Los ficheros de la tabla, en orden; FicheroNoValido si un patrón no encuentra ninguno."""
    carpeta = Path(carpeta)
    rutas: list[Path] = []
    for patron in t.patrones:
        encontrados = sorted(p for p in carpeta.glob(patron) if p.is_file())
        if not encontrados:
            raise FicheroNoValido(f"{t.nombre}: no hay ningún fichero {patron} en {carpeta}/")
        rutas += [p for p in encontrados if p not in rutas]
    return rutas


def _separador(muestra: str) -> str:
    """El separador de la muestra: el que detecta csv.Sniffer entre los admitidos o, si duda, el
    que más aparece en la cabecera (una sola columna: «,»)."""
    try:
        return csv.Sniffer().sniff(muestra, delimiters="".join(SEPARADORES)).delimiter
    except csv.Error:
        cabecera = muestra.splitlines()[0] if muestra else ""
        cuenta = {s: cabecera.count(s) for s in SEPARADORES}
        mejor = max(cuenta, key=cuenta.get)
        return mejor if cuenta[mejor] else ","


def _decodifica(ruta: Path, codificacion: str):
    """Abre el fichero; con utf-8 quita el BOM si lo hay."""
    cod = "utf-8-sig" if codecs.lookup(codificacion).name == "utf-8" else codificacion
    return ruta.open(encoding=cod, newline="")


def _no_es(ruta: Path, codificacion: str, exc: UnicodeDecodeError) -> FicheroNoValido:
    return FicheroNoValido(
        f"{ruta.name} no está en {codificacion} (byte {exc.start}): vuelve a exportarlo como "
        "«CSV UTF-8», conviértelo (iconv -f cp1252 -t utf-8 fichero.csv > fichero-utf8.csv) o "
        "indica su codificación en el contrato (codificacion: cp1252)"
    )


def leer_csv(
    ruta: Path, separador: str | None = None, codificacion: str = "utf-8"
) -> Iterator[dict[str, str]]:
    """Lee un CSV (UTF-8 con o sin BOM salvo que se indique otra codificación) con el separador
    indicado o detectado («,», «;», tabulador o «|»). FicheroNoValido con el fichero y la línea
    si no se puede decodificar, si la cabecera repite o deja sin nombre una columna o si una fila
    no tiene tantos campos como la cabecera."""
    ruta = Path(ruta)
    try:
        with _decodifica(ruta, codificacion) as f:
            sep = separador or _separador(f.read(65536))
            f.seek(0)
            lector = csv.reader(f, delimiter=sep)
            cabecera = next(lector, None)
            if not cabecera:
                raise FicheroNoValido(f"{ruta.name}: está vacío (no tiene cabecera)")
            if any(not c.strip() for c in cabecera):
                raise FicheroNoValido(f"{ruta.name}: la cabecera tiene una columna sin nombre")
            if len(set(cabecera)) != len(cabecera):
                raise FicheroNoValido(f"{ruta.name}: la cabecera repite una columna")
            for campos in lector:
                if not campos:
                    continue  # línea en blanco
                if len(campos) != len(cabecera):
                    raise FicheroNoValido(
                        f"{ruta.name}, línea {lector.line_num}: {len(campos)} campos y la "
                        f"cabecera tiene {len(cabecera)} (¿un separador dentro de un valor sin "
                        "comillas, o una fila partida?)"
                    )
                yield dict(zip(cabecera, campos, strict=True))
    except UnicodeDecodeError as exc:
        raise _no_es(ruta, codificacion, exc) from None


def cabecera_de(ruta: Path, separador: str | None = None, codificacion: str = "utf-8") -> list:
    ruta = Path(ruta)
    try:
        with _decodifica(ruta, codificacion) as f:
            sep = separador or _separador(f.read(65536))
            f.seek(0)
            return next(csv.reader(f, delimiter=sep), None) or []
    except UnicodeDecodeError as exc:
        raise _no_es(ruta, codificacion, exc) from None


def filas_de_ficheros(carpeta: Path, t: TablaContrato, instante: datetime) -> Iterator[dict]:
    """Las filas de los ficheros de la tabla tal cual, con su linaje: _loaded_at (el instante de
    la ejecución), _origen («fichero:<ruta dentro de datos/>») y _fila (número de línea)."""
    carpeta = Path(carpeta)
    for ruta in ficheros_de(carpeta, t):
        origen = f"fichero:{ruta.relative_to(carpeta).as_posix()}"
        for n, fila in enumerate(leer_csv(ruta, t.separador, t.codificacion), start=2):
            yield {**fila, "_loaded_at": instante, "_origen": origen, "_fila": n}


# --- Comprobaciones ---


@dataclass(frozen=True)
class Hallazgo:
    nivel: Literal["error", "aviso", "info"]
    tabla: str | None
    mensaje: str


def _error(tabla, mensaje) -> Hallazgo:
    return Hallazgo("error", tabla, mensaje)


def _aviso(tabla, mensaje) -> Hallazgo:
    return Hallazgo("aviso", tabla, mensaje)


def _columnas_de(conn, esquema: str, tabla: str) -> set[str] | None:
    """Columnas de esquema.tabla, o None si la tabla no existe."""
    filas = conn.execute(
        "select column_name from information_schema.columns "
        "where table_schema = %s and table_name = %s",
        (esquema, tabla),
    ).fetchall()
    return {f[0] for f in filas} or None


def _tipos_de(conn, esquema: str, tabla: str) -> dict[str, str]:
    return dict(
        conn.execute(
            "select column_name, data_type from information_schema.columns "
            "where table_schema = %s and table_name = %s order by ordinal_position",
            (esquema, tabla),
        ).fetchall()
    )


def _id(esquema: str, tabla: str) -> sql.Composed:
    return sql.SQL("{}.{}").format(sql.Identifier(esquema), sql.Identifier(tabla))


def _lista_id(columnas) -> sql.Composed:
    return sql.SQL(", ").join(sql.Identifier(c) for c in columnas)


def _es_de_dlt(conn, esquema: str, tabla: str, columnas: set[str]) -> list[Hallazgo]:
    """La tabla la ha cargado dlt: tiene _dlt_load_id y todas sus filas vienen de cargas
    completas de raw._dlt_loads."""
    if "_dlt_load_id" not in columnas:
        return [_error(tabla, "no la ha cargado dlt (falta _dlt_load_id)")]
    if _columnas_de(conn, esquema, "_dlt_loads") is None:
        return [_error(tabla, f"no la ha cargado dlt (falta {esquema}._dlt_loads)")]
    (n,) = conn.execute(
        sql.SQL(
            "select count(*) from {} r where not exists (select 1 from {} l where "
            "l.load_id = r._dlt_load_id and l.status = 0)"
        ).format(_id(esquema, tabla), _id(esquema, "_dlt_loads"))
    ).fetchone()
    if n:
        return [_error(tabla, f"{n} filas que no vienen de una carga completa de dlt")]
    return []


def comprobar_esquema(
    conn, esquema: str, contrato: ContratoCarga, origen: str | None = None, dlt: bool = True
) -> list[Hallazgo]:
    """Cada tabla del contrato existe en el esquema, la ha cargado dlt, tiene sus columnas y el
    linaje (_loaded_at y _origen no nulos; _origen igual a «origen» si se indica) y su clave
    cumple lo que pide su disposición: merge, única y sin nulos; append, única con el
    incremental; replace, única (admite nulos). Avisa de las columnas de raw que no están en el
    contrato y de las tablas hijas que crea dlt. Con dlt=False (un cargador sin dlt), no exige
    que las haya cargado dlt."""
    hallazgos: list[Hallazgo] = []
    origenes: dict[str, list[str]] = {}
    for t in contrato.tablas:
        columnas = _columnas_de(conn, esquema, t.nombre)
        if columnas is None:
            hallazgos.append(_error(t.nombre, f"falta la tabla {esquema}.{t.nombre}"))
            continue
        if dlt:
            hallazgos += _es_de_dlt(conn, esquema, t.nombre, columnas)
        faltan = [c for c in (*t.columnas, *LINAJE) if c not in columnas]
        faltan += [c for c in t.clave if c not in columnas and c not in faltan]
        hallazgos += [_error(t.nombre, f"falta la columna {c}") for c in faltan]
        sobran = sorted(
            c
            for c in columnas
            if c not in t.columnas and c not in (*LINAJE, "_fila") and not c.startswith("_dlt_")
        )
        if sobran:
            hallazgos.append(
                _aviso(t.nombre, "columnas en raw y no en el contrato: " + ", ".join(sobran))
            )
        hijas = [
            f[0]
            for f in conn.execute(
                "select table_name from information_schema.tables where table_schema = %s "
                "and table_name like %s order by 1",
                (esquema, t.nombre.replace("_", r"\_") + r"\_\_%"),
            ).fetchall()
        ]
        if hijas:
            hallazgos.append(
                _aviso(
                    t.nombre,
                    f"dlt ha creado {', '.join(hijas)}: un valor anidado (lista o JSON) que dlt "
                    "separa en otra tabla",
                )
            )
        tabla = _id(esquema, t.nombre)
        if "_loaded_at" in columnas:
            (n,) = conn.execute(
                sql.SQL("select count(*) from {} where _loaded_at is null").format(tabla)
            ).fetchone()
            if n:
                hallazgos.append(_error(t.nombre, f"{n} filas sin _loaded_at"))
        if "_origen" in columnas:
            if origen is None:
                consulta = sql.SQL("select count(*) from {} where _origen is null").format(tabla)
                texto = "{n} filas sin _origen"
            else:
                consulta = sql.SQL(
                    "select count(*) from {} where _origen is distinct from {}"
                ).format(tabla, sql.Literal(origen))
                texto = "{n} filas con _origen distinto de «" + origen + "»"
            (n,) = conn.execute(consulta).fetchone()
            if n:
                hallazgos.append(_error(t.nombre, texto.format(n=n)))
            for (valor,) in conn.execute(
                sql.SQL("select distinct _origen from {} where _origen is not null").format(tabla)
            ):
                origenes.setdefault(valor, []).append(t.nombre)
        if any(c not in columnas for c in t.clave_foto):
            continue
        clave = _lista_id(t.clave_foto)
        # Con replace (la clave admite nulos), como un unique de PostgreSQL: una clave con algún
        # nulo no se repite con otra. Con merge y append cuentan todas las filas.
        completas = (
            sql.SQL(" and ").join(
                sql.SQL("{} is not null").format(sql.Identifier(c)) for c in t.clave_foto
            )
            if t.disposicion == "replace"
            else sql.SQL("true")
        )
        (repetidas,) = conn.execute(
            sql.SQL(
                "select count(*) from (select 1 from {} where {} group by {} having count(*) > 1) r"
            ).format(tabla, completas, clave)
        ).fetchone()
        if repetidas:
            que = "claves (con el incremental)" if t.clave_foto != t.clave else "claves"
            hallazgos.append(_error(t.nombre, f"{repetidas} {que} repetidas"))
        if t.disposicion != "replace":
            nulas = sql.SQL(" or ").join(
                sql.SQL("{} is null").format(sql.Identifier(c)) for c in t.clave
            )
            (n,) = conn.execute(
                sql.SQL("select count(*) from {} where {}").format(tabla, nulas)
            ).fetchone()
            if n:
                hallazgos.append(
                    _error(
                        t.nombre,
                        f"{n} filas con la clave nula (con {t.disposicion} la clave no admite "
                        "nulos; replace sí)",
                    )
                )
        (total,) = conn.execute(sql.SQL("select count(*) from {}").format(tabla)).fetchone()
        if not total:
            hallazgos.append(_aviso(t.nombre, "la tabla está vacía"))
    for valor, tablas in origenes.items():
        if len(tablas) > 1 and origen is None:  # con «origen», es lo pedido
            hallazgos.append(
                _aviso(
                    None,
                    f"_origen «{valor}» se repite en {', '.join(tablas)}: no dice de dónde viene "
                    "cada tabla (p. ej. proyecto_origen.<esquema>.<tabla>)",
                )
            )
    return hallazgos


def comprobar_registro(
    conn, fuente: str, contrato: ContratoCarga, registro: str = "meta.carga"
) -> list[Hallazgo]:
    """La última fila de cada tabla en el registro (mayor id con esa fuente) es una carga
    correcta: estado ok o instantanea, fin no anterior al inicio y filas ≥ 0."""
    esquema, _, nombre = registro.rpartition(".")
    if _columnas_de(conn, esquema or "public", nombre) is None:
        return [_error(None, f"falta el registro de cargas {registro}")]
    hallazgos: list[Hallazgo] = []
    for t in contrato.tablas:
        ultima = conn.execute(
            sql.SQL(
                "select estado, inicio, fin, filas from {} where fuente = %s and tabla = %s "
                "order by id desc limit 1"
            ).format(_id(esquema or "public", nombre)),
            (fuente, t.nombre),
        ).fetchone()
        if ultima is None:
            hallazgos.append(_error(t.nombre, "sin registro de cargas"))
            continue
        estado, inicio, fin, filas = ultima
        if estado not in ("ok", "instantanea"):
            hallazgos.append(_error(t.nombre, f"la última carga terminó en estado «{estado}»"))
        elif fin is None or fin < inicio:
            hallazgos.append(
                _error(t.nombre, "la última carga no anota un fin posterior al inicio")
            )
        elif filas is None or filas < 0:
            hallazgos.append(_error(t.nombre, "la última carga no anota sus filas (≥ 0)"))
    return hallazgos


def ultimo_registro(conn, registro: str = "meta.carga") -> int:
    """El mayor id del registro (0 si está vacío o no existe)."""
    esquema, _, nombre = registro.rpartition(".")
    if _columnas_de(conn, esquema or "public", nombre) is None:
        return 0
    (n,) = conn.execute(
        sql.SQL("select coalesce(max(id), 0) from {}").format(_id(esquema or "public", nombre))
    ).fetchone()
    return n


def lecturas(conn, fuente: str, contrato: ContratoCarga, desde: int) -> dict[str, list]:
    """Por tabla, las filas leídas que anota meta.carga en cada ejecución posterior a «desde»,
    en orden (None si la ejecución terminó en error)."""
    res: dict[str, list] = {t.nombre: [] for t in contrato.tablas}
    for tabla, estado, filas in conn.execute(
        "select tabla, estado, filas from meta.carga where fuente = %s and id > %s order by id",
        (fuente, desde),
    ):
        if tabla in res:
            res[tabla].append(filas if estado in ("ok", "instantanea") else None)
    return res


# Por debajo, una tabla pequeña que el vivo reescribe casi entera entre las dos ejecuciones podría
# parecer releída: no se aplican la regla del 90 % ni la de «tantas como la primera».
MIN_FILAS_RELECTURA = 1000


def contar_filas(conn, esquema: str, contrato: ContratoCarga) -> dict[str, int]:
    """Por tabla, sus filas en el esquema (0 si aún no existe)."""
    res: dict[str, int] = {}
    for t in contrato.tablas:
        if _columnas_de(conn, esquema, t.nombre) is None:
            res[t.nombre] = 0
            continue
        (res[t.nombre],) = conn.execute(
            sql.SQL("select count(*) from {}").format(_id(esquema, t.nombre))
        ).fetchone()
    return res


def comprobar_lecturas(
    leidas: dict[str, list],
    contrato: ContratoCarga,
    nulos: dict[str, int] | None = None,
    vivo: bool = False,
    antes: dict[str, int] | None = None,
    despues: dict[str, int] | None = None,
) -> list[Hallazgo]:
    """Informa de las filas leídas por cada ejecución y exige que una tabla incremental no lea
    nada en la segunda (el origen no ha cambiado entre medias). Si el origen tiene cursores
    nulos que se incluyen en cada lectura, es un aviso.

    Con un origen vivo (que sigue cambiando entre las dos ejecuciones), la segunda lee lo que
    cambió entre medias, que puede ser más que lo que leyó la primera si esta ya era incremental
    (había cursor de una carga anterior: «antes», las filas de cada tabla antes de la primera
    ejecución, no es 0). Por eso solo es un error (salvo en las de replace, que se releen
    siempre) que la segunda lea casi toda la tabla («despues», sus filas tras la segunda, si
    tiene al menos MIN_FILAS_RELECTURA) o, si la primera fue la carga completa (tabla vacía
    antes) y la tabla tiene al menos MIN_FILAS_RELECTURA filas, tanto como ella."""
    nulos = nulos or {}
    hallazgos: list[Hallazgo] = []
    for t in contrato.tablas:
        filas = leidas.get(t.nombre, [])
        texto = ", ".join("error" if f is None else str(f) for f in filas) or "ninguna"
        hallazgos.append(Hallazgo("info", t.nombre, f"filas leídas por ejecución: {texto}"))
        if vivo:
            if not (
                t.incremental
                and t.disposicion != "replace"
                and len(filas) >= 2
                and filas[-2] is not None
                and filas[-1]
            ):
                continue
            total = (despues or {}).get(t.nombre, 0)
            completa = antes is None or not antes.get(t.nombre)
            if total >= MIN_FILAS_RELECTURA and filas[-1] * 10 >= total * 9:
                hallazgos.append(
                    _error(
                        t.nombre,
                        f"la segunda ejecución leyó {filas[-1]} filas de las {total} de la "
                        "tabla: relee la tabla entera en vez de seguir el cursor (guarda el "
                        "cursor de la última página y empieza por él la siguiente vez)",
                    )
                )
            elif completa and total >= MIN_FILAS_RELECTURA and filas[-2] and filas[-1] >= filas[-2]:
                hallazgos.append(
                    _error(
                        t.nombre,
                        f"la segunda ejecución leyó {filas[-1]} filas, tantas como la primera "
                        "(la carga completa): o relee la tabla entera en vez de seguir el "
                        "cursor, o se queda en la primera página (sigue el cursor mientras "
                        "hay_mas)",
                    )
                )
            continue
        if t.incremental and len(filas) >= 2 and filas[-1]:
            mensaje = (
                f"la segunda ejecución leyó {filas[-1]} filas sin cambios en el origen: con "
                f"incremental sobre {t.incremental} debería leer 0"
            )
            if nulos.get(t.nombre, 0) >= filas[-1]:
                hallazgos.append(_aviso(t.nombre, mensaje + " (salvo las de cursor nulo)"))
            else:
                hallazgos.append(_error(t.nombre, mensaje))
    return hallazgos


def comprobar_actualizaciones(
    leidas: dict[str, list], antes: dict, despues: dict, contrato: ContratoCarga
) -> list[Hallazgo]:
    """Con el origen vivo, que la segunda ejecución aplique lo que lee. La API entrega cada fila
    cambiada una sola vez por sincronización, en su versión vigente: en una tabla merge con
    incremental, cada fila que lee la segunda ejecución es una clave nueva o trae una versión
    posterior a la que dejó la primera. Si en raw (fotos «antes» y «despues» de la segunda, como
    las de foto) hay menos claves nuevas o con una versión posterior que filas leídas, la carga
    pierde actualizaciones (p. ej. un upsert «on conflict do nothing») o relee filas que ya
    tenía. La referencia no lo ve: es de antes de las ejecuciones y nunca trae la versión nueva."""
    hallazgos: list[Hallazgo] = []
    for t in contrato.tablas:
        filas = leidas.get(t.nombre, [])
        if not (
            t.incremental
            and t.clave
            and t.disposicion == "merge"
            and len(filas) >= 2
            and filas[-2] is not None
            and filas[-1]
        ):
            continue
        a, d = antes.get(t.nombre, {}), despues.get(t.nombre, {})
        nuevas = len(d.keys() - a.keys())
        subidas = sum(
            1
            for k in a.keys() & d.keys()
            if d[k][0] is not None and (a[k][0] is None or d[k][0] > a[k][0])
        )
        if filas[-1] > nuevas + subidas:
            hallazgos.append(
                _error(
                    t.nombre,
                    f"la segunda ejecución leyó {filas[-1]} filas, pero tras ella solo {nuevas} "
                    f"claves son nuevas y {subidas} tienen una versión posterior "
                    f"de {t.incremental}: no aplica lo que lee (¿un upsert que no actualiza, "
                    "como «on conflict do nothing»?) o relee filas que ya tenía (¿guarda el "
                    "cursor de la última página?)",
                )
            )
    return hallazgos


class FotoTabla(dict):
    """Foto de una tabla: clave → (valor incremental o None, md5). ``filas`` cuenta las filas de
    verdad: con claves repetidas es mayor que el número de claves (el diccionario las colapsa)."""

    def __init__(self, datos=(), filas: int | None = None):
        super().__init__(datos)
        self.filas = len(self) if filas is None else filas


def _filas(foto_tabla) -> int:
    return getattr(foto_tabla, "filas", len(foto_tabla))


def foto(conn, esquema: str, contrato: ContratoCarga) -> dict[str, dict[tuple, tuple[object, str]]]:
    """Por tabla: clave → (valor incremental o None, md5 de todas las columnas de raw salvo
    _loaded_at, _dlt_load_id y _dlt_id), como FotoTabla (que cuenta también las filas). Con
    append, la clave lleva también el incremental. Una tabla que no existe o a la que le faltan
    columnas queda vacía (comprobar_esquema lo explica)."""
    resultado: dict[str, dict[tuple, tuple[object, str]]] = {}
    for t in contrato.tablas:
        tipos = _tipos_de(conn, esquema, t.nombre)
        if any(c not in tipos for c in (*t.columnas, *t.clave)):
            resultado[t.nombre] = FotoTabla()
            continue
        huella = [c for c in tipos if c not in FUERA_DE_LA_HUELLA]
        incremental = sql.Identifier(t.incremental) if t.incremental else sql.SQL("null")
        consulta = sql.SQL("select {}, {}, md5(row({})::text) from {}").format(
            _lista_id(t.clave_foto), incremental, _lista_id(huella), _id(esquema, t.nombre)
        )
        n = len(t.clave_foto)
        filas = conn.execute(consulta).fetchall()
        resultado[t.nombre] = FotoTabla(
            {tuple(f[:n]): (f[n], f[n + 1]) for f in filas}, filas=len(filas)
        )
    return resultado


def foto_contrato(conn, esquema: str, contrato: ContratoCarga) -> dict[str, FotoTabla]:
    """Como foto, pero la huella es solo de las columnas del contrato, con los valores
    normalizados (_normal): sirve para comparar dos cargas del mismo origen hechas por motores
    distintos, con otro linaje y quizá otros tipos parecidos (numeric(10,2) y numeric)."""
    resultado: dict[str, FotoTabla] = {}
    for t in contrato.tablas:
        tipos = _tipos_de(conn, esquema, t.nombre)
        if any(c not in tipos for c in (*t.columnas, *t.clave)):
            resultado[t.nombre] = FotoTabla()
            continue
        incremental = sql.Identifier(t.incremental) if t.incremental else sql.SQL("null")
        consulta = sql.SQL("select {}, {}, {} from {}").format(
            _lista_id(t.clave_foto) if t.clave_foto else sql.SQL("null"),
            incremental,
            _lista_id(t.columnas),
            _id(esquema, t.nombre),
        )
        n = len(t.clave_foto) or 1
        datos, filas = {}, 0
        for f in _recorrer(conn, consulta):
            clave = tuple(_normal(v) for v in f[:n]) if t.clave_foto else ()
            datos[clave] = (f[n], _huella(f[n + 1 :]))
            filas += 1
        resultado[t.nombre] = FotoTabla(datos, filas=filas)
    return resultado


def comprobar_idempotencia(antes: dict, despues: dict, contrato: ContratoCarga) -> list[Hallazgo]:
    """Compara la foto tras la primera ejecución con la de tras la segunda. Con columna
    incremental se admiten filas nuevas posteriores a la primera carga (el origen cambió); sin
    ella, las dos fotos deben ser iguales."""
    hallazgos: list[Hallazgo] = []
    for t in contrato.tablas:
        a, d = antes.get(t.nombre, {}), despues.get(t.nombre, {})
        duplicadas = (_filas(d) - len(d)) - (_filas(a) - len(a))
        if duplicadas > 0:
            hallazgos.append(_error(t.nombre, f"la segunda ejecución duplicó {duplicadas} filas"))
        if t.incremental is None:
            distintas = len(a.keys() ^ d.keys()) + sum(
                1 for k in a.keys() & d.keys() if a[k] != d[k]
            )
            if distintas:
                hallazgos.append(_error(t.nombre, f"la segunda ejecución cambió {distintas} filas"))
            continue
        valores = [v[0] for v in a.values() if v[0] is not None]
        corte = max(valores) if valores else None
        borradas = len(a.keys() - d.keys())
        if borradas:
            hallazgos.append(_error(t.nombre, f"la segunda ejecución borró {borradas} filas"))
        cambiadas = sum(1 for k in a.keys() & d.keys() if a[k][0] == d[k][0] and a[k][1] != d[k][1])
        if cambiadas:
            hallazgos.append(_error(t.nombre, f"{cambiadas} filas cambiaron sin una versión nueva"))
        retroceden = sum(
            1
            for k in a.keys() & d.keys()
            if a[k][0] is not None and (d[k][0] is None or d[k][0] < a[k][0])
        )
        if retroceden:
            hallazgos.append(
                _error(
                    t.nombre,
                    f"{retroceden} filas con una versión anterior a la de la primera carga: la "
                    "segunda ejecución reescribe historia",
                )
            )
        viejas = sum(
            1
            for k in d.keys() - a.keys()
            if corte is not None and (d[k][0] is None or d[k][0] <= corte)
        )
        if viejas:
            hallazgos.append(
                _error(
                    t.nombre,
                    f"{viejas} filas nuevas anteriores a la primera carga: la segunda ejecución "
                    "duplica o reescribe historia",
                )
            )
    return hallazgos


def comprobar_equivalencia(a: dict, b: dict, contrato: ContratoCarga) -> list[Hallazgo]:
    """Compara dos cargas del mismo origen (a, la referencia; b, la comparada), como fotos de
    foto_contrato. Con clave e incremental, hasta el corte común (el menor de los dos máximos del
    incremental): cada fila de a anterior al corte está en b con su versión o una posterior, y
    con la misma versión, con los mismos valores; y en b no sobran filas anteriores al corte.
    Sin incremental, compara todas las filas; sin clave, solo cuántas hay."""
    hallazgos: list[Hallazgo] = []
    for t in contrato.tablas:
        fa, fb = a.get(t.nombre, {}), b.get(t.nombre, {})
        if not t.clave:
            hallazgos.append(_aviso(t.nombre, "sin clave: solo se compara el número de filas"))
            if _filas(fa) != _filas(fb):
                hallazgos.append(
                    _error(
                        t.nombre,
                        f"{_filas(fa)} filas en la referencia y {_filas(fb)} en el esquema "
                        "comparado",
                    )
                )
            continue
        maximos = [
            max((v[0] for v in f.values() if v[0] is not None), default=None) for f in (fa, fb)
        ]
        if t.incremental and None not in maximos and type(maximos[0]) is not type(maximos[1]):
            hallazgos.append(
                _error(
                    t.nombre,
                    f"{t.incremental} no tiene el mismo tipo en la referencia y en el esquema "
                    "comparado: usa el tipo de /tablas",
                )
            )
            continue
        corte = min(maximos) if t.incremental and None not in maximos else None

        def antes(version, corte=corte) -> bool:
            return corte is None or version is None or version <= corte

        faltan = antiguas = distintas = 0
        for k, (version, huella) in fa.items():
            if not antes(version):
                continue
            if k not in fb:
                faltan += 1
            elif t.incremental and version is not None and fb[k][0] is not None:
                if fb[k][0] < version:
                    antiguas += 1
                elif fb[k][0] == version and fb[k][1] != huella:
                    distintas += 1
            elif fb[k][1] != huella and (fb[k][0] == version or not t.incremental):
                distintas += 1
        sobran = sum(1 for k, (version, _) in fb.items() if antes(version) and k not in fa)
        donde = "anteriores al corte común" if corte is not None else "de la referencia"
        if faltan:
            hallazgos.append(
                _error(t.nombre, f"{faltan} filas {donde} faltan en el esquema comparado")
            )
        if antiguas:
            hallazgos.append(
                _error(t.nombre, f"{antiguas} filas son más antiguas que en la referencia")
            )
        if distintas:
            hallazgos.append(
                _error(t.nombre, f"{distintas} filas con la misma versión tienen valores distintos")
            )
        if sobran:
            donde = (
                "anteriores al corte común"
                if corte is not None
                else "que no están en la referencia"
            )
            hallazgos.append(
                _error(t.nombre, f"{sobran} filas {donde} sobran en el esquema comparado")
            )
    return hallazgos


def avisos_de_corte(
    a: dict, b: dict, contrato: ContratoCarga, cargada_despues: bool = False
) -> list[Hallazgo]:
    """El punto ciego de comprobar_equivalencia: si el esquema comparado (b) llega a un
    incremental menor que la referencia (a), el corte común baja y sus filas posteriores no se
    comparan. Con la referencia cargada antes, eso es sospechoso (p. ej. una carga que se para en
    la primera página): un aviso por tabla.

    Con «cargada_despues» (la parte guiada: el comprobador acaba de ejecutar dos veces la carga
    comparada, después de la referencia, y el reloj del origen solo avanza), es un error: una
    carga correcta llega al corte que le aplicó la API, que no es anterior al de la referencia
    (salvo que la referencia sea de una siembra anterior del origen)."""
    hallazgos: list[Hallazgo] = []
    for t in contrato.tablas:
        if not t.incremental or not t.clave:
            continue
        ma, mb = (
            max((v[0] for v in f.get(t.nombre, {}).values() if v[0] is not None), default=None)
            for f in (a, b)
        )
        if ma is None or mb is None or type(ma) is not type(mb) or not mb < ma:
            continue
        if cargada_despues:
            hallazgos.append(
                _error(
                    t.nombre,
                    f"el esquema comparado llega hasta {mb} y la referencia, cargada antes, hasta "
                    f"{ma}: la carga se para antes del corte que aplicó la API (¿se queda en "
                    "la primera página o no sigue el cursor mientras hay_mas?), o la referencia "
                    "(raw_pms) es de antes de una nueva siembra del profesor: recárgala con "
                    "make el SOLO=pms REINICIAR=1 en platform/",
                )
            )
            continue
        hallazgos.append(
            _aviso(
                t.nombre,
                f"el esquema comparado llega hasta {mb} y la referencia hasta {ma}: las filas "
                "posteriores no se comparan y pueden faltar (¿la carga se para antes de "
                "hay_mas = false?)",
            )
        )
    return hallazgos


# --- Conciliación de raw con el origen ---

_NULO = "\x00nulo"


def _normal(v) -> str:
    """Un valor en texto comparable entre bases y tipos parecidos (12.5 y 12.500000000, un
    instante en cualquier zona, un JSON con otro orden de claves)."""
    if v is None:
        return _NULO
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int | Decimal):
        d = Decimal(v)
        if d.is_nan() or d.is_infinite():
            return str(d)
        d = d.normalize()
        return "0" if d.is_zero() else format(d, "f")
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=UTC)).astimezone(UTC).isoformat()
    if isinstance(v, date | time):
        return v.isoformat()
    if isinstance(v, dict | list):
        return json.dumps(v, sort_keys=True, ensure_ascii=False, default=str)
    if isinstance(v, bytes | bytearray | memoryview):
        return bytes(v).hex()
    return str(v)


def _como(texto: str, tipo: str):
    """Un valor de un CSV convertido al tipo con el que dlt lo dejó en raw (dlt detecta, por
    ejemplo, los instantes ISO y los guarda como timestamp)."""
    if texto == "" and tipo not in ("text", "character varying", "character"):
        return None
    try:
        if tipo.startswith("timestamp"):
            try:
                return datetime.fromisoformat(texto)
            except ValueError:
                import pendulum

                return pendulum.parse(texto)
        if tipo == "date":
            return date.fromisoformat(texto)
        if tipo in ("bigint", "integer", "smallint", "numeric"):
            return Decimal(texto)
        if tipo in ("double precision", "real"):
            return float(texto)
        if tipo == "boolean":
            return texto.strip().lower() in ("true", "t", "1", "yes", "y")
        if tipo in ("json", "jsonb"):
            return json.loads(texto)
    except (ValueError, InvalidOperation, TypeError):
        return texto
    return texto


def _huella(valores) -> bytes:
    return hashlib.md5("\x1f".join(_normal(v) for v in valores).encode()).digest()


@dataclass
class Lado:
    """Filas de un lado de la conciliación: (clave normalizada, huella de las columnas)."""

    filas: list[tuple[tuple, bytes]] = field(default_factory=list)


def _recorrer(conn, consulta) -> Iterator[tuple]:
    """Las filas de la consulta sin traerlas todas a la vez (cursor de servidor dentro de una
    transacción; con autocommit, cursor normal)."""
    if conn.autocommit:
        yield from conn.execute(consulta)
        return
    with conn.cursor(name="conciliacion") as cur:
        cur.itersize = 5000
        cur.execute(consulta)
        yield from cur


def _lado(conn, consulta, n: int) -> Lado:
    lado = Lado()
    for f in _recorrer(conn, consulta):
        lado.filas.append((tuple(_normal(v) for v in f[:n]), _huella(f[n:])))
    return lado


def _filas_de_raw(conn, esquema: str, t: TablaContrato) -> Lado:
    consulta = sql.SQL("select {}, {} from {}").format(
        _lista_id(t.clave), _lista_id(t.columnas), _id(esquema, t.nombre)
    )
    return _lado(conn, consulta, len(t.clave))


def _valor(fila: dict, nombres: dict[str, str], c: str, tipos: dict[str, str]):
    if c in LINAJE_FICHERO:
        return fila[c]
    return _como(fila[nombres[c]], tipos.get(c, "text"))


def _filas_de_ficheros(carpeta: Path, t: TablaContrato, tipos: dict[str, str]) -> Lado:
    lado = Lado()
    nombres: dict[str, str] = {}
    for fila in filas_de_ficheros(carpeta, t, datetime.now(UTC)):
        if not nombres or any(c not in fila for c in nombres.values()):
            nombres = {normalizar(c): c for c in fila if c not in LINAJE}
        clave = tuple(_normal(_valor(fila, nombres, c, tipos)) for c in t.clave)
        lado.filas.append((clave, _huella(_valor(fila, nombres, c, tipos) for c in t.columnas)))
    return lado


def _filas_del_origen(conn, t: TablaContrato) -> tuple[Lado | None, list[Hallazgo]]:
    columnas = _tipos_de(conn, t.esquema_origen, t.nombre)
    if not columnas:
        return None, [_error(t.nombre, f"no está en proyecto_origen (esquema {t.esquema_origen})")]
    hallazgos: list[Hallazgo] = []
    nombres = {normalizar(c): c for c in columnas}
    faltan = [c for c in (*t.columnas, *t.clave) if c not in nombres]
    if faltan:
        return None, [
            _error(t.nombre, f"la columna {c} del contrato no está en el origen") for c in faltan
        ]
    consulta = sql.SQL("select {}, {} from {}").format(
        _lista_id(nombres[c] for c in t.clave),
        _lista_id(nombres[c] for c in t.columnas),
        _id(t.esquema_origen, t.nombre),
    )
    return _lado(conn, consulta, len(t.clave)), hallazgos


def _comparar(t: TablaContrato, origen: Lado, raw: Lado, donde: str) -> list[Hallazgo]:
    hallazgos: list[Hallazgo] = []
    hallazgos.append(
        Hallazgo(
            "info", t.nombre, f"{donde}: {len(origen.filas)} filas; raw: {len(raw.filas)} filas"
        )
    )
    if t.disposicion == "replace":
        o, r = Counter(origen.filas), Counter(raw.filas)
        faltan, sobran = sum((o - r).values()), sum((r - o).values())
        if faltan:
            hallazgos.append(
                _error(t.nombre, f"{faltan} filas de {donde} no están en raw tal cual")
            )
        if sobran:
            hallazgos.append(_error(t.nombre, f"{sobran} filas de raw no están en {donde}"))
        return hallazgos
    o = Counter(k for k, _ in origen.filas)
    repetidas = sum(1 for v in o.values() if v > 1)
    if repetidas:
        hallazgos.append(
            _error(
                t.nombre,
                f"{repetidas} claves se repiten en {donde}: no identifican una fila (con "
                f"{t.disposicion}, unas filas pisan a otras)",
            )
        )
    en_raw: dict[tuple, set[bytes]] = {}
    for k, h in raw.filas:
        en_raw.setdefault(k, set()).add(h)
    faltan = sum(1 for k, _ in origen.filas if k not in en_raw)
    distintas = sum(1 for k, h in origen.filas if k in en_raw and h not in en_raw[k])
    if faltan:
        hallazgos.append(_error(t.nombre, f"{faltan} filas de {donde} no han llegado a raw"))
    if distintas:
        pista = f" (¿{t.incremental} cambia en cada modificación?)" if t.incremental else ""
        hallazgos.append(
            _error(t.nombre, f"{distintas} filas de raw no coinciden con {donde}{pista}")
        )
    borradas = len(en_raw.keys() - o.keys())
    if borradas:
        hallazgos.append(
            _aviso(
                t.nombre,
                f"{borradas} claves de raw ya no están en {donde}: {t.disposicion} no propaga "
                "los borrados (decide si importa y dilo en la nota)",
            )
        )
    return hallazgos


def contar_cursores_nulos(conn, contrato: ContratoCarga) -> dict[str, int]:
    """Filas del origen con la columna incremental nula, por tabla (solo tablas de origen)."""
    nulos: dict[str, int] = {}
    for t in contrato.tablas:
        if t.fichero or not t.incremental:
            continue
        nombres = {normalizar(c): c for c in _tipos_de(conn, t.esquema_origen, t.nombre)}
        if t.incremental not in nombres:
            continue
        (n,) = conn.execute(
            sql.SQL("select count(*) from {} where {} is null").format(
                _id(t.esquema_origen, t.nombre), sql.Identifier(nombres[t.incremental])
            )
        ).fetchone()
        nulos[t.nombre] = n
    return nulos


def conciliar(
    conn_raw, conn_origen, carpeta: Path, esquema: str, contrato: ContratoCarga
) -> list[Hallazgo]:
    """raw coincide con su origen en las columnas del contrato: con replace, las mismas filas;
    con merge, cada fila del origen está en raw con sus valores (las claves que ya no están en
    el origen son un aviso: borrados); con append, cada fila del origen está entre las versiones
    de raw. Avisa de las columnas del origen que no llegan a raw y de los cursores nulos."""
    hallazgos: list[Hallazgo] = []
    for t in contrato.tablas:
        tipos = _tipos_de(conn_raw, esquema, t.nombre)
        if any(c not in tipos for c in (*t.columnas, *t.clave)):
            continue  # comprobar_esquema ya lo explica
        if t.fichero:
            try:
                origen = _filas_de_ficheros(carpeta, t, tipos)
            except FicheroNoValido as exc:
                hallazgos.append(_error(t.nombre, str(exc)))
                continue
            donde = "sus ficheros"
            cabeceras = set()
            for ruta in ficheros_de(carpeta, t):
                cabeceras |= {normalizar(c) for c in cabecera_de(ruta, t.separador, t.codificacion)}
        else:
            if conn_origen is None:
                continue
            origen, extra = _filas_del_origen(conn_origen, t)
            hallazgos += extra
            if origen is None:
                continue
            donde = "el origen"
            cabeceras = {normalizar(c) for c in _tipos_de(conn_origen, t.esquema_origen, t.nombre)}
            n = contar_cursores_nulos(conn_origen, ContratoCarga((t,))).get(t.nombre, 0)
            if n:
                hallazgos.append(
                    _aviso(
                        t.nombre,
                        f"{n} filas del origen con {t.incremental} nulo: dlt falla con ellas "
                        "salvo que decidas on_cursor_value_missing (dilo en la nota)",
                    )
                )
        no_llegan = sorted(c for c in cabeceras if c not in tipos)
        if no_llegan:
            hallazgos.append(
                _aviso(t.nombre, f"columnas de {donde} que no llegan a raw: {', '.join(no_llegan)}")
            )
        hallazgos += _comparar(t, origen, _filas_de_raw(conn_raw, esquema, t), donde)
    return hallazgos


def comprobar_ficheros(carpeta: Path, contrato: ContratoCarga) -> list[Hallazgo]:
    """Sin base de datos: los ficheros del contrato existen y se leen enteros, sus cabeceras
    (normalizadas como hace dlt) traen las columnas del contrato sin colisiones y la columna
    incremental parece una fecha ISO (dlt compara el texto)."""
    hallazgos: list[Hallazgo] = []
    for t in contrato.tablas:
        if not t.fichero:
            continue
        try:
            rutas = ficheros_de(carpeta, t)
            nombres: dict[str, str] = {}
            for ruta in rutas:
                cabecera = cabecera_de(ruta, t.separador, t.codificacion)
                normal = [normalizar(c) for c in cabecera]
                for n, c in Counter(normal).items():
                    if c > 1:
                        hallazgos.append(
                            _error(t.nombre, f"{ruta.name}: varias cabeceras quedan como {n}")
                        )
                for c, n in zip(cabecera, normal, strict=True):
                    nombres.setdefault(n, c)
                for c in t.columnas:
                    if c not in normal:
                        hallazgos.append(
                            _error(
                                t.nombre,
                                f"{ruta.name} no trae la columna {c} (make columnas enseña los "
                                "nombres que deja dlt)",
                            )
                        )
            filas = 0
            raros = 0
            for fila in filas_de_ficheros(carpeta, t, datetime.now(UTC)):
                filas += 1
                if t.incremental and t.incremental in nombres:
                    v = fila.get(nombres[t.incremental], "")
                    if v and not re.match(r"^\d{4}-\d{2}-\d{2}", v):
                        raros += 1
            if raros:
                hallazgos.append(
                    _aviso(
                        t.nombre,
                        f"{raros} valores de {t.incremental} no son fechas ISO (aaaa-mm-dd…): dlt "
                        "compara el texto y el orden no será el de las fechas",
                    )
                )
            if not filas:
                hallazgos.append(_aviso(t.nombre, "sus ficheros no tienen filas"))
        except FicheroNoValido as exc:
            hallazgos.append(_error(t.nombre, str(exc)))
    return hallazgos


def columnas_de_ficheros(rutas: list[Path], separador=None, codificacion="utf-8") -> list[str]:
    """Líneas «cabecera → nombre en raw» de cada fichero, con las colisiones señaladas."""
    lineas = []
    for ruta in rutas:
        cabecera = cabecera_de(ruta, separador, codificacion)
        normal = [normalizar(c) for c in cabecera]
        cuenta = Counter(normal)
        lineas.append(f"{ruta}:")
        for c, n in zip(cabecera, normal, strict=True):
            marca = "   ← ERROR: otra cabecera queda igual" if cuenta[n] > 1 else ""
            lineas.append(f"  {c!r:<28} → {n}{marca}")
    return lineas


# --- Línea de órdenes ---


class FaltaVariable(RuntimeError):
    """Falta una variable de entorno del kit (normalmente, porque no hay .env)."""

    def __init__(self, nombre: str, pista: str = "¿has ejecutado make base, que crea .env?"):
        super().__init__(f"falta la variable {nombre} ({pista})")


def url_base(base: str = "destino") -> str:
    """URL de la base de destino («proyecto») o de la de origen («proyecto_origen»), con usuario
    y contraseña escapados (una contraseña con @, / o : no rompe la URL)."""
    if base not in ("destino", "origen"):
        raise ValueError(f"base desconocida: {base} (usa destino u origen)")
    if not os.environ.get("PROYECTO_CLAVE"):
        raise FaltaVariable("PROYECTO_CLAVE")
    nombre = (
        os.environ.get("PROYECTO_BASE", "proyecto")
        if base == "destino"
        else os.environ.get("PROYECTO_BASE_ORIGEN", "proyecto_origen")
    )
    usuario = quote(os.environ.get("PROYECTO_USUARIO", "proyecto"), safe="")
    clave = quote(os.environ["PROYECTO_CLAVE"], safe="")
    return (
        f"postgresql://{usuario}:{clave}@{os.environ.get('PROYECTO_HOST', '127.0.0.1')}:"
        f"{os.environ.get('PROYECTO_PUERTO', '5440')}/{quote(nombre, safe='')}"
    )


def _imprimir(hallazgos: list[Hallazgo], ok: str) -> int:
    for h in hallazgos:
        nivel = {"error": "ERROR", "aviso": "AVISO", "info": "INFO"}[h.nivel]
        print(f"{nivel} {h.tabla}: {h.mensaje}" if h.tabla else f"{nivel} {h.mensaje}")
    errores = sum(h.nivel == "error" for h in hallazgos)
    if not errores:
        print(f"OK {ok}")
    return errores


def _ejecutar(orden: str) -> bool:
    partes = shlex.split(orden)
    try:
        r = subprocess.run(partes)
    except FileNotFoundError:
        print(f"ERROR no se encuentra «{partes[0]}»: instálalo (README del kit, Requisitos)")
        return False
    if r.returncode != 0:
        print(f"ERROR la orden de carga falló (código {r.returncode})")
    return r.returncode == 0


def _datos_por_omision() -> Path:
    return Path(os.environ.get("PROYECTO_DATOS", "datos"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Comprueba el contrato de carga de tu proyecto.")
    ap.add_argument("--contrato", type=Path, default=Path("contrato.yml"))
    ap.add_argument("--datos", type=Path, default=None, help="carpeta de tus ficheros")
    ap.add_argument("--solo-contrato", action="store_true", help="valida sin conectarse")
    ap.add_argument(
        "--columnas",
        nargs="*",
        type=Path,
        default=None,
        help="enseña cómo quedan en raw las cabeceras de estos CSV (o de los del contrato)",
    )
    dsn = ap.add_mutually_exclusive_group()
    dsn.add_argument("--dsn", help="URL de la base (por omisión, la de PROYECTO_*)")
    dsn.add_argument("--dsn-variable", help="variable de entorno con la URL de la base")
    ap.add_argument("--dsn-origen", help="URL de la base de origen (por omisión, la de PROYECTO_*)")
    ap.add_argument("--sin-origen", action="store_true", help="no concilia raw con el origen")
    ap.add_argument("--esquema", default="raw")
    ap.add_argument("--fuente", default="proyecto", help="fuente de las filas de meta.carga")
    ap.add_argument("--origen", help="valor que debe tener _origen en todas las filas")
    ap.add_argument("--orden", help="orden de carga: se ejecuta dos veces (idempotencia)")
    ap.add_argument(
        "--contrato-atlantida",
        action="store_true",
        help="parte guiada: el contrato sale de GET /tablas de la API (SIM_API_URL); sin dlt, "
        "sin proyecto_origen y con el origen vivo",
    )
    ap.add_argument(
        "--referencia", help="esquema con otra carga del mismo origen con el que compararla"
    )
    args = ap.parse_args(argv)
    guiada = args.contrato_atlantida
    if guiada:
        args.sin_origen = True
    datos = args.datos or _datos_por_omision()
    try:
        if args.columnas:
            for linea in columnas_de_ficheros(args.columnas):
                print(linea)
            return 0
        contrato = contrato_atlantida() if guiada else contrato_desde_yaml(args.contrato)
        if args.columnas is not None:
            rutas = []
            for t in contrato.tablas:
                if t.fichero:
                    for linea in columnas_de_ficheros(
                        ficheros_de(datos, t), t.separador, t.codificacion
                    ):
                        print(linea)
                    rutas.append(t.nombre)
            if not rutas:
                print("Ninguna tabla del contrato tiene «fichero»: usa make columnas F=fichero.csv")
            return 0
        if args.solo_contrato:
            print(f"OK contrato válido: {len(contrato.tablas)} tablas")
            if any(t.fichero for t in contrato.tablas):
                if not datos.is_dir():
                    print(f"AVISO no existe {datos}/: no compruebo los ficheros")
                    return 0
                if _imprimir(
                    comprobar_ficheros(datos, contrato),
                    f"ficheros: los de {datos}/ se leen y traen las columnas del contrato",
                ):
                    return 1
            return 0
        if args.dsn_variable and not os.environ.get(args.dsn_variable):
            raise FaltaVariable(args.dsn_variable)
        url = args.dsn or (os.environ[args.dsn_variable] if args.dsn_variable else url_base())
        errores = 0
        if args.orden:
            partes = shlex.split(args.orden)
            if not partes or shutil.which(partes[0]) is None:
                print(
                    f"ERROR no se encuentra «{partes[0] if partes else ''}»: instálalo (README "
                    "del kit, Requisitos)"
                )
                return 1
        conn_origen = None
        ref = None
        if not args.sin_origen and any(not t.fichero for t in contrato.tablas):
            conn_origen = psycopg.connect(args.dsn_origen or url_base("origen"))
        try:
            if args.orden:
                with psycopg.connect(url) as c:
                    desde = ultimo_registro(c)
                    previas = contar_filas(c, args.esquema, contrato)
                    if args.referencia:  # antes de ejecutar: otra carga de la referencia en
                        # paralelo no la adelanta respecto a la comparada
                        ref = foto_contrato(c, args.referencia, contrato)
                fotos = []
                for _ in range(2):
                    if not _ejecutar(args.orden):
                        return 1
                    with psycopg.connect(url) as c:
                        fotos.append(foto(c, args.esquema, contrato))
                errores += _imprimir(
                    comprobar_idempotencia(*fotos, contrato),
                    "idempotencia: la segunda ejecución no duplica ni reescribe",
                )
                with psycopg.connect(url) as c:
                    leidas = lecturas(c, args.fuente, contrato, desde)
                nulos = contar_cursores_nulos(conn_origen, contrato) if conn_origen else {}
                errores += _imprimir(
                    comprobar_lecturas(
                        leidas,
                        contrato,
                        nulos,
                        vivo=guiada,
                        antes=previas,
                        despues={k: _filas(v) for k, v in fotos[-1].items()},
                    ),
                    "lecturas: la segunda ejecución sigue el cursor (solo lee lo nuevo)"
                    if guiada
                    else "lecturas: sin cambios en el origen, la segunda ejecución incremental no "
                    "lee nada",
                )
                if guiada:
                    errores += _imprimir(
                        comprobar_actualizaciones(leidas, *fotos, contrato),
                        "actualizaciones: lo que lee la segunda ejecución queda en "
                        f"{args.esquema} (claves nuevas o versiones posteriores)",
                    )
            with psycopg.connect(url) as c:
                errores += _imprimir(
                    comprobar_esquema(c, args.esquema, contrato, args.origen, dlt=not guiada),
                    f"esquema: tablas, columnas, claves y linaje en {args.esquema}",
                )
                errores += _imprimir(
                    comprobar_registro(c, args.fuente, contrato),
                    f"registro: la última carga de cada tabla en meta.carga (fuente {args.fuente})",
                )
                if not args.sin_origen:
                    errores += _imprimir(
                        conciliar(c, conn_origen, datos, args.esquema, contrato),
                        f"origen: {args.esquema} coincide con proyecto_origen y {datos}/",
                    )
                if args.referencia:
                    if ref is None:
                        ref = foto_contrato(c, args.referencia, contrato)
                    lab = foto_contrato(c, args.esquema, contrato)
                    errores += _imprimir(
                        avisos_de_corte(
                            ref, lab, contrato, cargada_despues=guiada and bool(args.orden)
                        )
                        + comprobar_equivalencia(ref, lab, contrato),
                        f"equivalencia: {args.esquema} coincide con {args.referencia} hasta el "
                        "corte común",
                    )
        finally:
            if conn_origen is not None:
                conn_origen.close()
    except (ContratoNoValido, FaltaVariable, FicheroNoValido) as exc:
        print(f"ERROR {exc}")
        return 1
    except psycopg.Error as exc:  # su texto puede llevar la conexión: solo el tipo
        print(
            f"ERROR no se pudo usar la base ({type(exc).__name__}): ¿está levantada y es la "
            "contraseña de .env?"
        )
        return 1
    except OSError as exc:
        print(f"ERROR {exc}")
        return 1
    if errores:
        print(f"ERROR contrato de carga: {errores} errores")
        return 1
    print(f"OK contrato de carga: {args.esquema} ({len(contrato.tablas)} tablas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
