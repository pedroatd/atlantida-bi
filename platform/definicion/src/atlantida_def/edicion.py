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
            f"«{orden}» necesita el simulador del PMS, que no forma parte de la edición del "
            "alumnado: tus datos de Atlántida llegan de la API del profesor (ORIGEN_PMS=api en "
            "platform/.env; ver platform/el/README.md)."
        )
