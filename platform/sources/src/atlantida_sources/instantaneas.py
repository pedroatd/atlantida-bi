"""Lectura de instantáneas versionadas: comprueba el sha256 del manifiesto y el contrato."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .contrato import validar
from .manifiesto import RUTA_SNAPSHOTS, leer_manifiesto, sha256_fichero


class InstantaneaCorrupta(Exception):
    """La instantánea no coincide con su manifiesto o con el contrato."""


def leer(fuente: str, directorio: Path | None = None) -> pd.DataFrame:
    directorio = directorio or RUTA_SNAPSHOTS
    entrada = leer_manifiesto(directorio).get(fuente)
    if entrada is None:
        raise InstantaneaCorrupta(f"{fuente}: no figura en el manifiesto de {directorio}")
    fichero = directorio / entrada.fichero
    if not fichero.is_file() or sha256_fichero(fichero) != entrada.sha256:
        raise InstantaneaCorrupta(
            f"{fuente}: {fichero.name} no coincide con su sha256 del manifiesto"
        )
    # Solo la cadena vacía es nulo: códigos como "NA" (Namibia) deben sobrevivir como texto.
    df = pd.read_csv(fichero, keep_default_na=False, na_values=[""])
    try:
        df = validar(fuente, df)
    except ValueError as exc:
        raise InstantaneaCorrupta(str(exc)) from exc
    if "fecha" in df.columns:
        df["fecha"] = pd.to_datetime(df["fecha"])
    return df
