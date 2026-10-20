"""Enmascarado de secretos en textos que se muestran o se registran (salidas de órdenes, errores
de las cargas en Dagster)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import quote, quote_plus

_NOMBRE_SECRETO = re.compile(r"PASSWORD|(^|_)(TOKEN|SECRET|SAL|KEY)(_|$)", re.IGNORECASE)


def enmascarar(texto: str, env: Mapping[str, str]) -> str:
    """Sustituye por *** los valores secretos del entorno (claves, tokens, sal) y sus formas
    codificadas para URL. Ignora valores de menos de 4 caracteres para no mutilar el texto."""
    formas: set[str] = set()
    for nombre, valor in env.items():
        if len(valor) >= 4 and _NOMBRE_SECRETO.search(nombre):
            formas |= {valor, quote(valor, safe=""), quote(valor), quote_plus(valor)}
    for forma in sorted(formas, key=len, reverse=True):
        texto = texto.replace(forma, "***")
    return texto
