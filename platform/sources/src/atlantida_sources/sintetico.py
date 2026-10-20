"""Instantáneas SINTÉTICAS de contingencia, solo si una fuente real no responde al implementar.
Se marcan sintetico=true en el manifiesto; nunca sustituyen en silencio a una fuente real."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from .istac import MERCADOS_ISTAC, TERRITORIOS

_PERFIL = {
    "NORD": [3, 3, 2.6, 1.6, 0.5, 0.3, 0.4, 0.5, 0.6, 1.4, 2.4, 3],
    "DE": [1.4, 1.4, 1.3, 1.2, 0.8, 0.7, 0.9, 0.9, 0.9, 1.2, 1.3, 1.3],
}


def istac_sintetico(desde: str, hasta: str) -> pd.DataFrame:
    rng = np.random.default_rng(1)
    meses = pd.period_range(desde, hasta, freq="M")
    filas = [
        {
            "periodo_mes": str(m),
            "isla": isla,
            "pais_origen": p,
            "llegadas": int(20000 * _PERFIL.get(p, [1] * 12)[m.month - 1] * rng.lognormal(0, 0.05)),
        }
        for m in meses
        for isla in TERRITORIOS.values()
        for p in MERCADOS_ISTAC.values()
    ]
    return pd.DataFrame(filas)


def bce_sintetico(desde: date, hasta: date) -> pd.DataFrame:
    rng = np.random.default_rng(2)
    dias = pd.bdate_range(desde, hasta)
    base = {"GBP": 0.86, "SEK": 11.3, "NOK": 11.5, "DKK": 7.46}
    return pd.concat(
        [
            pd.DataFrame(
                {
                    "fecha": dias.strftime("%Y-%m-%d"),
                    "divisa": d,
                    "tipo_cambio": np.round(
                        b * np.exp(np.cumsum(rng.normal(0, 0.003, len(dias)))), 5
                    ),
                }
            )
            for d, b in base.items()
        ],
        ignore_index=True,
    )


def meteo_sintetico(desde: date, hasta: date) -> pd.DataFrame:
    from .meteo import ESTACIONES  # meteo.py llega en la Task 3

    rng = np.random.default_rng(3)
    dias = pd.date_range(desde, hasta)
    doy = dias.dayofyear.to_numpy()
    partes = []
    for est in ESTACIONES.values():
        p_lluvia = 0.02 + 0.10 * (np.cos(2 * np.pi * (doy - 15) / 365) > 0.3)
        partes.append(
            pd.DataFrame(
                {
                    "fecha": dias.strftime("%Y-%m-%d"),
                    "isla": est.isla,
                    "estacion": f"SIN-{est.idema}",
                    "precipitacion": np.where(
                        rng.random(len(dias)) < p_lluvia, rng.gamma(1.2, 5, len(dias)), 0
                    ).round(1),
                    "temperatura_maxima": (
                        24
                        - 3.5 * np.cos(2 * np.pi * (doy - 30) / 365)
                        + rng.normal(0, 1.2, len(dias))
                    ).round(1),
                }
            )
        )
    return pd.concat(partes, ignore_index=True)
