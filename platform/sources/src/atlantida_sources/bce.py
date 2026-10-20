"""Tipos de cambio de referencia del BCE (unidades de divisa por euro)."""

from __future__ import annotations

import io
from datetime import date

import httpx
import pandas as pd

from . import red

DIVISAS = ("GBP", "SEK", "NOK", "DKK")
LICENCIA = "Reutilización libre citando la fuente (política de reutilización del BCE)"
ATRIBUCION = "Fuente: Banco Central Europeo, ECB Data Portal (EXR)"


def url(desde: date, hasta: date) -> str:
    return (
        "https://data-api.ecb.europa.eu/service/data/EXR/D."
        + "+".join(DIVISAS)
        + f".EUR.SP00.A?startPeriod={desde}&endPeriod={hasta}&format=csvdata"
    )


def decodificar_csv(texto: str) -> pd.DataFrame:
    df = pd.read_csv(io.StringIO(texto), usecols=["CURRENCY", "TIME_PERIOD", "OBS_VALUE"])
    df = df.dropna(subset=["OBS_VALUE"])
    return pd.DataFrame(
        {"fecha": df.TIME_PERIOD, "divisa": df.CURRENCY, "tipo_cambio": df.OBS_VALUE.astype(float)}
    ).reset_index(drop=True)


def descargar(desde: date, hasta: date, cliente: httpx.Client | None = None) -> pd.DataFrame:
    if cliente is None:
        with httpx.Client(timeout=60) as propio:
            return descargar(desde, hasta, propio)
    return red.get_decodificado(cliente, url(desde, hasta), lambda r: decodificar_csv(r.text))
