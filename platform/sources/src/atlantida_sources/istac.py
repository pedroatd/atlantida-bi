"""Llegadas de turistas por isla y lugar de residencia (ISTAC, FRONTUR-Canarias)."""

from __future__ import annotations

import httpx
import pandas as pd

from . import red

DATASET = "E16028B_000011"
URL = (
    "https://datos.canarias.es/api/estadisticas/statistical-resources/v1.0/datasets/ISTAC/"
    f"{DATASET}/~latest"
)
LICENCIA = (
    "Condiciones generales de reutilización del ISTAC (Ley 37/2007): uso comercial y no "
    "comercial citando la fuente; ver https://www.gobiernodecanarias.org/istac/aviso_legal.html"
)
ATRIBUCION = "Fuente: Instituto Canario de Estadística (ISTAC), FRONTUR-Canarias"
TERRITORIOS = {
    "ES709": "Tenerife",
    "ES705": "Gran Canaria",
    "ES708": "Lanzarote",
    "ES704": "Fuerteventura",
}
# Solo mercados disjuntos (sin totales), para que las llegadas se puedan sumar.
MERCADOS_ISTAC = {
    "ES_XIC": "ES",
    "GB": "GB",
    "DE": "DE",
    "5100_L1": "NORD",
    "NL": "NL",
    "BE": "BE",
    "FR": "FR",
    "IE": "IE",
    "IT": "IT",
    "5000_XES_O": "OTROS",
}


def decodificar(doc: dict) -> pd.DataFrame:
    """Las observaciones son una cadena «a | b | …» en orden fila mayor: el índice plano se
    calcula con el índice de representación de cada dimensión, en el orden de
    ``data.dimensions``."""
    dims = doc["data"]["dimensions"]["dimension"]
    nombres = [d["dimensionId"] for d in dims]
    codigos = [[None] * len(d["representations"]["representation"]) for d in dims]
    for i, d in enumerate(dims):
        for r in d["representations"]["representation"]:
            codigos[i][r["index"]] = r["code"]
    obs = [o.strip() for o in doc["data"]["observations"].split("|")]
    indice = pd.MultiIndex.from_product(codigos, names=nombres)
    if len(obs) != len(indice):
        raise ValueError(f"ISTAC: {len(obs)} observaciones para {len(indice)} celdas")
    df = pd.DataFrame({"valor": obs}, index=indice).reset_index()
    df = df[
        (df.TIPO_VIAJERO == "TURISTA")
        & (df.MEDIDAS == "TURISTAS")
        & df.TERRITORIO.isin(TERRITORIOS)
        & df.LUGAR_RESIDENCIA.isin(MERCADOS_ISTAC)
        & (df.valor != "")
    ]
    return pd.DataFrame(
        {
            "periodo_mes": df.TIME_PERIOD.str.replace("-M", "-", regex=False),
            "isla": df.TERRITORIO.map(TERRITORIOS),
            "pais_origen": df.LUGAR_RESIDENCIA.map(MERCADOS_ISTAC),
            "llegadas": _enteros(df.valor),
        }
    ).reset_index(drop=True)


def _enteros(valores: pd.Series) -> pd.Series:
    """Convierte a entero sin truncar: marcadores no numéricos o decimales son un error claro."""
    numeros = pd.to_numeric(valores, errors="coerce")
    malos = valores[numeros.isna()]
    if not malos.empty:
        raise ValueError(f"ISTAC: valores no numéricos {sorted(set(malos))[:5]}")
    if (numeros % 1 != 0).any():
        raise ValueError(
            f"ISTAC: llegadas con decimales {sorted(set(valores[numeros % 1 != 0]))[:5]}"
        )
    return numeros.astype("int64")


def descargar(cliente: httpx.Client | None = None, desde: str = "2021-01") -> pd.DataFrame:
    if cliente is None:
        with httpx.Client(timeout=120) as propio:
            return descargar(propio, desde)
    df = red.get_decodificado(
        cliente, URL, lambda r: decodificar(r.json()), headers={"Accept": "application/json"}
    )
    return df[df.periodo_mes >= desde].reset_index(drop=True)
