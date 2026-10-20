"""Peticiones HTTP con reintentos y espera exponencial: las fuentes públicas fallan a veces."""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx

REINTENTABLES = {429, 500, 502, 503, 504}


def get(
    cliente: httpx.Client,
    url: str,
    *,
    intentos: int = 4,
    espera: float = 2.0,
    dormir: Callable[[float], None] = time.sleep,
    **kw,
) -> httpx.Response:
    """GET con reintentos. Los mensajes llevan host y ruta, nunca la consulta ni las cabeceras."""
    destino = f"{httpx.URL(url).host}{httpx.URL(url).path}"
    ultimo = "sin respuesta"
    for i in range(intentos):
        try:
            r = cliente.get(url, **kw)
        except httpx.TransportError as exc:
            ultimo = type(exc).__name__
        else:
            if r.status_code < 400:
                return r
            if r.status_code not in REINTENTABLES:
                raise RuntimeError(f"{destino}: HTTP {r.status_code}")
            ultimo = f"HTTP {r.status_code}"
        if i < intentos - 1:
            dormir(min(60.0, espera * 2**i))
    raise RuntimeError(f"{destino}: {ultimo} tras {intentos} intentos")


def get_decodificado(
    cliente: httpx.Client,
    url: str,
    decodificar: Callable[[httpx.Response], object],
    *,
    intentos: int = 4,
    espera: float = 2.0,
    dormir: Callable[[float], None] = time.sleep,
    **kw,
):
    """GET y decodificación juntos: un 200 con cuerpo truncado o no válido también se reintenta."""
    destino = f"{httpx.URL(url).host}{httpx.URL(url).path}"
    for i in range(intentos):
        r = get(cliente, url, intentos=intentos, espera=espera, dormir=dormir, **kw)
        try:
            return decodificar(r)
        except (ValueError, KeyError, TypeError):
            if i < intentos - 1:
                dormir(min(60.0, espera * 2**i))
    raise RuntimeError(f"{destino}: respuesta no válida o truncada tras {intentos} intentos")
