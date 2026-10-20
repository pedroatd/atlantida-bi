"""Manifiesto de las instantáneas: origen de cada fichero y comprobación de que no ha cambiado."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from .contrato import claves, validar

_PAQUETE = Path(__file__).resolve().parent


def _ruta_snapshots() -> Path:
    for candidata in (_PAQUETE / "snapshots", _PAQUETE.parents[1] / "snapshots"):
        if candidata.is_dir():
            return candidata
    return _PAQUETE.parents[1] / "snapshots"


RUTA_SNAPSHOTS = _ruta_snapshots()


@dataclass(frozen=True)
class Entrada:
    fuente: str
    fichero: str
    url: str
    licencia: str
    atribucion: str
    descargado: str
    sha256: str
    filas: int
    sintetico: bool
    nota: str


def sha256_fichero(ruta: Path) -> str:
    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def leer_manifiesto(directorio: Path | None = None) -> dict[str, Entrada]:
    ruta = (directorio or RUTA_SNAPSHOTS) / "manifiesto.json"
    if not ruta.is_file():
        return {}
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    return {k: Entrada(**v) for k, v in datos.items()}


def registrar(
    fuente: str,
    df: pd.DataFrame,
    *,
    url: str,
    licencia: str,
    atribucion: str,
    sintetico: bool = False,
    nota: str = "",
    directorio: Path | None = None,
    hoy: date | None = None,
) -> Entrada:
    """Valida ``df`` contra el contrato, lo escribe ordenado por clave y actualiza el manifiesto.

    El CSV y el manifiesto se escriben en dos pasos atómicos independientes: si el proceso muere
    entre ambos, el sha256 del manifiesto no coincide con el CSV y ``instantaneas.leer`` lo detecta.
    """
    directorio = directorio or RUTA_SNAPSHOTS
    directorio.mkdir(parents=True, exist_ok=True)
    df = validar(fuente, df).sort_values(claves(fuente)).reset_index(drop=True)
    fichero = directorio / f"{fuente}.csv"
    _escribir_atomico(fichero, df.to_csv(index=False, lineterminator="\n"))
    entrada = Entrada(
        fuente=fuente,
        fichero=fichero.name,
        url=url,
        licencia=licencia,
        atribucion=atribucion,
        descargado=(hoy or date.today()).isoformat(),
        sha256=sha256_fichero(fichero),
        filas=len(df),
        sintetico=sintetico,
        nota=nota,
    )
    manifiesto = {k: asdict(v) for k, v in leer_manifiesto(directorio).items()}
    manifiesto[fuente] = asdict(entrada)
    _escribir_atomico(
        directorio / "manifiesto.json",
        json.dumps(manifiesto, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return entrada


def _escribir_atomico(ruta: Path, texto: str) -> None:
    """Escribe en un temporal del mismo directorio y lo renombra: nunca queda a medias."""
    tmp = ruta.with_name(ruta.name + ".tmp")
    tmp.write_text(texto, encoding="utf-8")
    tmp.replace(ruta)
