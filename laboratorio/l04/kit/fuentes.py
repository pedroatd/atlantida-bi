"""Fuentes de dbt desde el contrato del L3 (make fuentes): escribe models/staging/_fuentes.yml
con una fuente «raw» (el esquema raw de tu base «proyecto»), una tabla por tabla del contrato,
sus columnas y las pruebas de su clave según la disposición: merge, única y sin nulos; append,
sin nulos y única con el incremental; replace, única (admite nulos, como en el L3). Marca las
columnas de «personales», que solo staging lee y seudonimiza. Si llega a la base, avisa de lo que
el contrato declara y raw no tiene, y de los datos personales que no son texto."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import yaml

TEXTUALES = {"text", "character varying", "character", "citext"}
SALIDA = Path("models/staging/_fuentes.yml")


class ContratoNoValido(ValueError):
    """El contrato del L3 no tiene lo que hace falta para declarar las fuentes."""


def _sin_comillas(nombre: str) -> bool:
    return re.fullmatch(r"[a-z_][a-z0-9_]*", nombre) is not None


def _citado(nombre: str) -> str:
    return nombre if _sin_comillas(nombre) else '"' + nombre.replace('"', '""') + '"'


def _lista(tabla: str, definicion: dict, campo: str) -> list[str]:
    valor = definicion.get(campo) or []
    if not isinstance(valor, list) or not all(isinstance(c, str) and c for c in valor):
        raise ContratoNoValido(f"{tabla}: «{campo}» debe ser una lista de columnas")
    return valor


def _tablas(contrato: dict) -> dict:
    tablas = contrato.get("tablas") if isinstance(contrato, dict) else None
    if not tablas:
        raise ContratoNoValido("contrato.yml: falta «tablas»")
    if not isinstance(tablas, dict) or not all(isinstance(d, dict) for d in tablas.values()):
        raise ContratoNoValido("contrato.yml: «tablas» debe ser un mapa nombre → definición")
    for nombre, d in tablas.items():
        columnas = _lista(nombre, d, "columnas")
        if not columnas:
            raise ContratoNoValido(f"{nombre}: falta «columnas»")
        if not _lista(nombre, d, "clave"):
            raise ContratoNoValido(f"{nombre}: falta «clave»")
        for campo in ("clave", "personales"):
            for c in _lista(nombre, d, campo):
                if c not in columnas:
                    raise ContratoNoValido(
                        f"{nombre}.{c}: «{campo}» nombra una columna que no está en «columnas»"
                    )
        incremental = d.get("incremental")
        if incremental is not None and incremental not in columnas:
            raise ContratoNoValido(f"{nombre}.{incremental}: «incremental» no está en «columnas»")
    return tablas


def _unica(columnas: list[str]) -> dict:
    """Prueba unique sobre varias columnas: una expresión (filas con algún nulo no cuentan)."""
    expresion = " || '|' || ".join(f"{_citado(c)}::text" for c in columnas)
    return {"unique": {"arguments": {"column_name": expresion}}}


def _descripcion_personal(tipo: str | None) -> str:
    texto = (
        "Dato personal (contrato del L3): en claro solo en raw. Seudonimízalo en staging con "
        "seudonimo('columna') o no lo uses."
    )
    if tipo and tipo not in TEXTUALES:
        texto += (
            f" Es de tipo {tipo}: seudonimo() lo convierte a texto, pero con pocos valores "
            "posibles (fechas, códigos) quien tenga la sal lo recupera por fuerza bruta; valora "
            "generalizarlo (solo el año, una zona) en vez de seudonimizarlo."
        )
    return texto


def generar(contrato: dict, tipos: dict | None = None) -> dict:
    """El YAML de «sources» de dbt (como diccionario) para el contrato del L3. «tipos», si se da,
    es {tabla: {columna: tipo de PostgreSQL}} de raw, y explica los personales que no son texto."""
    tipos = tipos or {}
    tablas = []
    for nombre, d in _tablas(contrato).items():
        clave, personales = d["clave"], set(d.get("personales") or ())
        disposicion = d.get("disposicion", "merge")
        incremental = d.get("incremental")
        pruebas_clave = [] if disposicion == "replace" else ["not_null"]
        unica = None  # columnas que no se repiten
        if disposicion in ("merge", "replace"):
            unica = clave
        elif incremental:
            unica = [*clave, incremental]
        columnas = []
        for c in d["columnas"]:
            columna: dict = {"name": c}
            if not _sin_comillas(c):
                columna["quote"] = True
            if c in personales:
                columna["description"] = _descripcion_personal(tipos.get(nombre, {}).get(c))
                columna["meta"] = {"personal": True}
            pruebas = list(pruebas_clave) if c in clave else []
            if unica == [c]:
                pruebas.append("unique")
            if pruebas:
                columna["data_tests"] = pruebas
            columnas.append(columna)
        tabla: dict = {"name": nombre}
        if not _sin_comillas(nombre):
            tabla["quoting"] = {"identifier": True}
        tabla["description"] = (
            f"raw.{nombre}: copia fiel cargada con el kit del L3 ({disposicion})."
        )
        tabla["columns"] = columnas
        if unica and len(unica) > 1:
            tabla["data_tests"] = [_unica(unica)]
        tablas.append(tabla)
    return {
        "version": 2,
        "sources": [
            {
                "name": "raw",
                "schema": "raw",
                "description": (
                    "Tu carga en crudo del L3 (make fuentes la declara desde contrato.yml). "
                    "Cada fila lleva _loaded_at y _origen. Solo staging lee raw."
                ),
                "tables": tablas,
            }
        ],
    }


def avisos(contrato: dict, tipos: dict) -> list[str]:
    """Lo que el contrato declara y raw no tiene, y los personales que no son texto, cada uno
    con su tabla y su columna."""
    resultado = []
    for nombre, d in _tablas(contrato).items():
        if nombre not in tipos:
            resultado.append(f"{nombre}: no está en raw (¿has cargado con el kit del L3?)")
            continue
        for c in d["columnas"]:
            if c not in tipos[nombre]:
                resultado.append(f"{nombre}.{c}: no está en raw.{nombre}")
        for c in d.get("personales") or ():
            tipo = tipos[nombre].get(c)
            if tipo and tipo not in TEXTUALES:
                resultado.append(
                    f"{nombre}.{c}: «personales» sobre una columna de tipo {tipo}; seudonimo() la "
                    "convierte a texto y, con pocos valores posibles, se recupera por fuerza "
                    "bruta: valora generalizarla"
                )
    return resultado


def leer_contrato(ruta: Path) -> dict:
    ruta = Path(ruta)
    if not ruta.is_file():
        raise ContratoNoValido(
            f"no encuentro {ruta}: el contrato del L3 está en el kit del L3 (L3_KIT)"
        )
    try:
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ContratoNoValido(
            f"{ruta.name}: no es YAML válido ({exc.__class__.__name__})"
        ) from None
    if not isinstance(datos, dict):
        raise ContratoNoValido(f"{ruta.name}: falta «tablas»")
    return datos


def conninfo() -> str:
    """Conexión a la base «proyecto» del kit del L3 (las variables de su .env)."""
    import psycopg

    if not os.environ.get("PROYECTO_CLAVE"):
        raise ContratoNoValido(
            "falta la variable PROYECTO_CLAVE: está en el .env del kit del L3; ejecuta las "
            "órdenes con make (lo lee de L3_KIT, por omisión ../l03-kit)"
        )
    return psycopg.conninfo.make_conninfo(
        host=os.environ.get("PROYECTO_HOST", "127.0.0.1"),
        port=os.environ.get("PROYECTO_PUERTO", "5440"),
        user=os.environ.get("PROYECTO_USUARIO", "proyecto"),
        password=os.environ["PROYECTO_CLAVE"],
        dbname=os.environ.get("PROYECTO_BASE", "proyecto"),
        connect_timeout=10,
    )


def tipos_de_raw() -> dict:
    import psycopg

    tipos: dict = {}
    with psycopg.connect(conninfo()) as c:
        for tabla, columna, tipo in c.execute(
            "select table_name, column_name, data_type from information_schema.columns "
            "where table_schema = 'raw' order by table_name, ordinal_position"
        ):
            tipos.setdefault(tabla, {})[columna] = tipo
    return tipos


def main(argv: list[str] | None = None) -> int:
    l3 = Path(os.environ.get("L3_KIT", "../l03-kit"))
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--contrato", type=Path, default=l3 / "contrato.yml")
    ap.add_argument("--salida", type=Path, default=SALIDA)
    ap.add_argument("--sin-base", action="store_true", help="no mira raw (tipos y tablas)")
    args = ap.parse_args(argv)
    try:
        contrato = leer_contrato(args.contrato)
        tipos = None
        if not args.sin_base:
            import psycopg

            try:
                tipos = tipos_de_raw()
            except psycopg.Error as exc:
                print(
                    f"AVISO no se pudo leer raw ({type(exc).__name__}): las fuentes salen solo "
                    "del contrato. ¿Está levantada la base (make base en el kit del L3)?",
                    file=sys.stderr,
                )
        fuentes = generar(contrato, tipos)
        for aviso in avisos(contrato, tipos) if tipos is not None else []:
            print(f"AVISO {aviso}")
    except ContratoNoValido as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    args.salida.parent.mkdir(parents=True, exist_ok=True)
    cabecera = (
        "# Generado con make fuentes desde el contrato del L3: vuelve a generarlo si cambias el\n"
        "# contrato. Puedes añadir descripciones, pero make fuentes las sobrescribe.\n"
    )
    args.salida.write_text(
        cabecera + yaml.safe_dump(fuentes, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8",
    )
    n = len(fuentes["sources"][0]["tables"])
    print(f"Escrito {args.salida} ({n} tablas de raw).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
