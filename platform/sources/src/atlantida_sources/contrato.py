"""Columnas de cada fuente externa según platform/definicion/contrato_externo.yml."""

from __future__ import annotations

import pandas as pd
from atlantida_def import cargar_contrato_externo


def claves(fuente: str) -> list[str]:
    return list(_contrato(fuente)["claves"])


def columnas(fuente: str) -> list[str]:
    c = _contrato(fuente)
    return list(c["claves"]) + list(c["valores"])


def _contrato(fuente: str) -> dict[str, list[str]]:
    contrato = cargar_contrato_externo()
    if fuente not in contrato:
        raise ValueError(f"fuente desconocida: {fuente} (contrato: {sorted(contrato)})")
    return contrato[fuente]


def validar(fuente: str, df: pd.DataFrame) -> pd.DataFrame:
    """Devuelve ``df`` con las columnas del contrato en orden; falla si no lo cumple."""
    esperadas = columnas(fuente)
    faltan = [c for c in esperadas if c not in df.columns]
    sobran = [c for c in df.columns if c not in esperadas]
    if faltan or sobran:
        raise ValueError(f"{fuente}: faltan {faltan}; sobran {sobran}")
    repetidas = df.duplicated(subset=claves(fuente))
    if repetidas.any():
        raise ValueError(
            f"{fuente}: {int(repetidas.sum())} filas repiten la clave {claves(fuente)}"
        )
    return df[esperadas].reset_index(drop=True)
