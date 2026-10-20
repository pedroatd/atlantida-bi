"""Carga del contrato del PMS y del documento de definición desde YAML.

Las rutas por defecto no dependen del directorio de trabajo: se buscan junto al
paquete instalado (rueda) y, si no están, en ``platform/definicion/`` (instalación
editable del *workspace*). Así funcionan igual desde la raíz del repositorio,
desde ``book/`` al renderizar el libro o desde un contenedor.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from .modelos import Definicion

_PAQUETE = Path(__file__).resolve().parent


def _ruta_por_defecto(nombre: str) -> Path:
    for candidata in (_PAQUETE / nombre, _PAQUETE.parents[1] / nombre):
        if candidata.is_file():
            return candidata
    raise FileNotFoundError(f"no se encuentra {nombre} junto a atlantida_def")


def _leer(ruta: Path | None, nombre: str) -> dict:
    ruta = Path(ruta) if ruta is not None else _ruta_por_defecto(nombre)
    with ruta.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def cargar_contrato(ruta: Path | None = None) -> dict[str, list[str]]:
    """Devuelve el contrato del PMS como ``{tabla: [columnas]}``."""
    return {t: list(cols) for t, cols in _leer(ruta, "contrato_pms.yml")["tablas"].items()}


def cargar_contrato_externo(ruta: Path | None = None) -> dict[str, dict[str, list[str]]]:
    """Devuelve el contrato de las fuentes externas: ``{fuente: {"claves": [...],
    "valores": [...]}}``."""
    fuentes = _leer(ruta, "contrato_externo.yml")["fuentes"]
    return {
        f: {"claves": list(c["claves"]), "valores": list(c["valores"])} for f, c in fuentes.items()
    }


def cargar_restricciones(ruta: Path | None = None) -> dict[str, list[str]]:
    """Devuelve los valores permitidos de cada enumeración: ``{"tabla.columna": [valores]}``."""
    return {k: list(v) for k, v in _leer(ruta, "contrato_pms.yml")["restricciones"].items()}


_COLUMNA_REGLA = {"guest_flag": "flag", "rate_restriction": "rule"}
"""Columna del PMS que recibe el valor de la regla de cada tabla de reverse ETL."""


def validar_contra_contrato(
    definicion: Definicion,
    contrato: dict[str, list[str]],
    externo: dict[str, dict[str, list[str]]] | None = None,
    restricciones: dict[str, list[str]] | None = None,
) -> None:
    """Contrasta la definición con los contratos.

    * Cada medida raw del PMS apunta a una ``tabla.columna`` del contrato del PMS y cada
      medida externa, a una columna (clave o valor) de una fuente del contrato externo.
    * Con ``restricciones``: la desagregación por régimen cubre exactamente los regímenes
      de ``rate_plan.board`` y el valor de cada regla de reverse ETL está en el vocabulario
      de su tabla (``guest_flag.flag`` o ``rate_restriction.rule``).
    """
    for m in definicion.medidas_raw:
        if m.fuente == "externa":
            if externo is None:
                continue
            if m.tabla not in externo:
                raise ValueError(
                    f"medida {m.id}: fuente externa desconocida {m.tabla!r} "
                    f"(contrato externo: {', '.join(sorted(externo))})"
                )
            if m.columna not in externo[m.tabla]["claves"] + externo[m.tabla]["valores"]:
                raise ValueError(
                    f"medida {m.id}: la columna {m.tabla}.{m.columna} no está en el contrato "
                    "externo"
                )
            continue
        if m.tabla not in contrato:
            raise ValueError(f"medida {m.id}: la tabla {m.tabla!r} no está en el contrato del PMS")
        if m.columna not in contrato[m.tabla]:
            raise ValueError(
                f"medida {m.id}: la columna {m.tabla}.{m.columna} no está en el contrato del PMS"
            )
    if restricciones is None:
        return
    regimenes = set(restricciones["rate_plan.board"])
    declarados = set(definicion.desagregacion_regimen)
    if declarados != regimenes:
        raise ValueError(
            f"desagregacion_regimen: faltan {sorted(regimenes - declarados)} y sobran "
            f"{sorted(declarados - regimenes)} frente a rate_plan.board del contrato"
        )
    for a in definicion.acciones:
        r = a.regla_pms
        if r is None:
            continue
        clave = f"{r.tabla}.{_COLUMNA_REGLA[r.tabla]}"
        if r.valor not in restricciones[clave]:
            raise ValueError(
                f"acción {a.id}: la regla {r.valor!r} no está en {clave} "
                f"({', '.join(restricciones[clave])})"
            )


def cargar_definicion(
    ruta: Path | None = None, contrato: Path | None = None, contrato_externo: Path | None = None
) -> Definicion:
    """Carga ``atlantida.yml`` (u otra definición), la valida y la contrasta con los contratos
    del PMS (``contrato_pms.yml``) y de las fuentes externas (``contrato_externo.yml``).

    Los errores de validación se elevan como ``ValueError`` (``ValidationError``
    de pydantic lo es) con un mensaje que nombra el elemento culpable.
    """
    datos = _leer(ruta, "atlantida.yml")
    try:
        definicion = Definicion.model_validate(datos)
    except ValidationError as e:
        raise ValueError(str(e)) from e
    validar_contra_contrato(
        definicion,
        cargar_contrato(contrato),
        cargar_contrato_externo(contrato_externo),
        cargar_restricciones(contrato),
    )
    return definicion
