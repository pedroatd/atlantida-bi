"""Lectura de platform/.env para las órdenes que se ejecutan fuera de Docker (uv run …), igual
que hace atlantida-sim. Dentro de Docker, Compose ya pasa las variables y no se pisa ninguna."""

from __future__ import annotations

import os
from collections.abc import MutableMapping
from pathlib import Path

from .errores import ErrorDeCarga


def _leer(ruta: Path) -> dict[str, str]:
    datos: dict[str, str] = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        clave, igual, valor = linea.removeprefix("export ").lstrip().partition("=")
        clave, valor = clave.strip(), valor.strip()
        if not igual or not clave:
            continue
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        elif " #" in valor:
            valor = valor.split(" #", 1)[0].rstrip()
        datos[clave] = valor
    return datos


def _candidatos(entorno: MutableMapping[str, str]) -> list[Path]:
    if entorno.get("EL_ENV_FILE"):
        return [Path(entorno["EL_ENV_FILE"])]
    rutas = [Path.cwd() / ".env", Path.cwd() / "platform" / ".env"]
    padres = Path(__file__).resolve().parents
    if len(padres) > 3:  # repo/platform (en una copia del repo; en la imagen no existe)
        rutas.append(padres[3] / ".env")
    return rutas


def cargar_env_file(entorno: MutableMapping[str, str] | None = None) -> Path | None:
    """Carga el primer .env disponible sin pisar lo ya definido en el entorno. Con EL_ENV_FILE,
    ese fichero manda y debe existir. Devuelve el fichero usado."""
    entorno = os.environ if entorno is None else entorno
    for ruta in _candidatos(entorno):
        if ruta.is_file():
            try:
                datos = _leer(ruta)
            except (OSError, UnicodeDecodeError) as exc:
                raise ErrorDeCarga(f"No se pudo leer {ruta}: {exc}") from exc
            for clave, valor in datos.items():
                entorno.setdefault(clave, valor)
            return ruta
    if entorno.get("EL_ENV_FILE"):
        raise ErrorDeCarga(f"EL_ENV_FILE={entorno['EL_ENV_FILE']!r} no existe.")
    return None
