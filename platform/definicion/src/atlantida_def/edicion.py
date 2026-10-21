"""Edición de la plataforma: completa (con el simulador del PMS) o del alumnado (sin él: el PMS
lo sirve el profesor por su API de cambios)."""

from __future__ import annotations

import importlib.util
import sys
from importlib.metadata import entry_points

# El paquete del simulador se anuncia con este punto de entrada (su pyproject.toml); la edición del
# alumnado no lo instala, así que no hace falta nombrar aquí su módulo.
GRUPO = "atlantida.edicion"


class EdicionSinSimulador(RuntimeError):
    codigo_salida = 2


class CapaPosterior(RuntimeError):
    """La orden es de una capa que esta copia de la edición del alumnado aún no trae."""

    codigo_salida = 2


def modulo_del_simulador() -> str | None:
    """El módulo que anuncia el punto de entrada «simulador» del grupo GRUPO, o None."""
    return next((ep.value for ep in entry_points(group=GRUPO, name="simulador")), None)


def simulador_disponible() -> bool:
    nombre = modulo_del_simulador()
    if nombre is None:
        return False
    if nombre in sys.modules:  # None: importación bloqueada (así lo simulan las pruebas)
        return sys.modules[nombre] is not None
    return importlib.util.find_spec(nombre) is not None


def requiere_simulador(orden: str) -> None:
    if not simulador_disponible():
        raise EdicionSinSimulador(
            f"«{orden}» es del profesor: necesita el simulador del PMS, que no forma parte de la "
            "edición del alumnado. Tus datos de Atlántida llegan de la API del profesor "
            "(ORIGEN_PMS=api en platform/.env; ver platform/el/README.md)."
        )


def del_simulador(submodulo: str, orden: str):
    """Un módulo del simulador (p. ej. «config»), importado por su punto de entrada: el código de
    las demás capas no nombra el paquete, que la edición del alumnado no trae. Sin él, la orden
    se niega con EdicionSinSimulador."""
    requiere_simulador(orden)
    return importlib.import_module(f"{modulo_del_simulador()}.{submodulo}")


def de_capa(modulo: str, orden: str, laboratorio: str):
    """Un módulo de una capa que la edición del alumnado trae a partir de un laboratorio (p. ej.
    la capa semántica): sin él, la orden se niega con CapaPosterior y dice con qué laboratorio
    llega, como la regla .DEFAULT del Makefile. Un fallo de importación dentro del módulo (una
    dependencia que falta) no se disfraza: se propaga tal cual."""
    try:
        return importlib.import_module(modulo)
    except ModuleNotFoundError as e:
        if e.name != modulo:
            raise
        raise CapaPosterior(
            f"«{orden}» llega con el laboratorio {laboratorio}: esta copia de la plataforma aún "
            "no trae esa capa."
        ) from None
