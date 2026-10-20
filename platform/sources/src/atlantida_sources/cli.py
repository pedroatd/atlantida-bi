"""atlantida-fuentes: actualiza (requiere Internet) o verifica las instantáneas externas."""

from __future__ import annotations

import argparse
import shutil
import sys
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from . import bce, festivos, istac, meteo, sintetico
from .instantaneas import InstantaneaCorrupta, leer
from .manifiesto import RUTA_SNAPSHOTS, leer_manifiesto, registrar

FUENTES = ("istac_frontur", "aemet_diario", "festivos", "bce_tipos")
# Celdas que el ISTAC publica vacías (verificado en su API el 2026-10-04); no son una descarga rota.
LAGUNAS_ISTAC = {("2021-05", "Fuerteventura", "IE")}
SIM_END = date(2026, 3, 31)  # las instantáneas deben cubrir al menos el horizonte simulado


def _istac(desde, hasta, sint):
    df = (
        sintetico.istac_sintetico(f"{desde:%Y-%m}", f"{hasta:%Y-%m}")
        if sint
        else istac.descargar(desde=f"{desde:%Y-%m}")
    )
    return df, {
        "url": istac.URL,
        "licencia": istac.LICENCIA,
        "atribucion": istac.ATRIBUCION,
        "nota": "TIPO_VIAJERO=TURISTA, MEDIDAS=TURISTAS; mercados disjuntos sin totales. "
        "Laguna de la fuente: sin dato Fuerteventura-IE en 2021-05.",
        "sintetico": sint,
    }


def _bce(desde, hasta, sint):
    df = sintetico.bce_sintetico(desde, hasta) if sint else bce.descargar(desde, hasta)
    return df, {
        "url": bce.url(desde, hasta),
        "licencia": bce.LICENCIA,
        "atribucion": bce.ATRIBUCION,
        "nota": "",
        "sintetico": sint,
    }


def _festivos(desde, hasta, sint):
    """Siempre real (reglas y librería): ``--sintetico`` no la etiqueta como sintética."""
    return festivos.generar(range(desde.year, hasta.year + 2)), {
        "url": "https://pypi.org/project/holidays/0.105/",
        "licencia": "MIT (librería holidays)",
        "atribucion": "python-holidays",
        "nota": (
            "Vacaciones escolares: reglas aproximadas (festivos.vacaciones_escolares). "
            "Ámbito insular:<isla> = patronas de Gran Canaria, Lanzarote y Fuerteventura "
            "(Tenerife no tiene fiesta insular oficial). El Carnaval de Canarias figura como "
            "semana escolar, no como festivo."
        ),
        "sintetico": False,
    }


PARCIALES_AEMET = RUTA_SNAPSHOTS / ".parciales" / "aemet"


def _meteo(desde, hasta, sint):
    if sint:
        df = sintetico.meteo_sintetico(desde, hasta)
        return df, {"url": "", "licencia": "", "atribucion": "", "nota": "", "sintetico": True}
    hasta = min(hasta, date.today() - timedelta(days=5))
    df, meta = meteo.descargar(
        desde,
        hasta,
        parciales=PARCIALES_AEMET,
        sin_datos=RUTA_SNAPSHOTS / "aemet_sin_datos.json",
    )
    return df, {**meta, "sintetico": False}


DESCARGADORES: dict[str, Callable[[date, date, bool], tuple[pd.DataFrame, dict]]] = {
    "istac_frontur": _istac,
    "bce_tipos": _bce,
    "festivos": _festivos,
    "aemet_diario": _meteo,
}


def comprobar_cobertura(fuente: str, df: pd.DataFrame, desde: date, hasta: date) -> None:
    """Una descarga incompleta no sustituye a la instantánea anterior."""
    if df.empty:
        raise ValueError(f"{fuente}: descarga vacía")
    if fuente == "istac_frontur":
        meses = pd.period_range(f"{desde:%Y-%m}", df.periodo_mes.max(), freq="M").astype(str)
        esperados = {
            (i, p) for i in istac.TERRITORIOS.values() for p in istac.MERCADOS_ISTAC.values()
        }
        pares = df.groupby("periodo_mes").apply(
            lambda g: set(zip(g.isla, g.pais_origen, strict=True)), include_groups=False
        )
        incompletos = [
            m
            for m in meses
            if not esperados - {(i, p) for (mm, i, p) in LAGUNAS_ISTAC if mm == m}
            <= pares.get(m, set())
        ]
        if incompletos:
            raise ValueError(
                f"istac_frontur: meses incompletos {incompletos[:6]} (faltan pares isla-país)"
            )
        if df.periodo_mes.max() < f"{min(hasta, SIM_END):%Y-%m}":
            raise ValueError(
                f"istac_frontur: el último mes ({df.periodo_mes.max()}) no llega a {SIM_END:%Y-%m}"
            )
    elif fuente == "bce_tipos":
        fin = pd.Timestamp(min(hasta, date.today())) - pd.Timedelta(days=7)
        for divisa in bce.DIVISAS:
            f = pd.to_datetime(df[df.divisa == divisa].fecha).sort_values()
            if f.empty:
                raise ValueError(f"bce_tipos: falta la serie de {divisa}")
            if f.min() > pd.Timestamp(desde) + pd.Timedelta(days=7):
                raise ValueError(
                    f"bce_tipos: la serie de {divisa} empieza tarde ({f.min():%Y-%m-%d})"
                )
            if f.max() < fin:
                raise ValueError(
                    f"bce_tipos: la serie de {divisa} termina pronto ({f.max():%Y-%m-%d})"
                )
            if f.diff().dt.days.max() > 7:
                raise ValueError(f"bce_tipos: la serie de {divisa} tiene huecos de más de 7 días")
    elif fuente == "aemet_diario":
        fin = min(hasta, date.today() - timedelta(days=10))
        dias = (fin - desde).days + 1
        for isla, g in df.groupby("isla"):
            validos = g.precipitacion.notna().sum()
            if validos < 0.97 * dias:
                raise ValueError(f"aemet_diario: {isla} tiene {validos} días con dato de {dias}")
    elif fuente == "festivos":
        anios = set(pd.to_datetime(df.fecha).dt.year)
        if not set(range(desde.year, hasta.year + 1)) <= anios:
            raise ValueError("festivos: faltan años")


def _actualizar(fuente, desde, hasta, directorio: Path, sint: bool) -> None:
    df, meta = DESCARGADORES[fuente](desde, hasta, sint)
    comprobar_cobertura(fuente, df, desde, hasta)
    if meta["sintetico"]:  # cada descargador declara si sus datos son sintéticos
        meta = {
            **meta,
            "nota": "SINTÉTICA: la fuente real no respondió al generar la instantánea. "
            + meta["nota"],
        }
    registrar(fuente, df, directorio=directorio, **meta)
    if fuente == "aemet_diario":
        shutil.rmtree(PARCIALES_AEMET, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="atlantida-fuentes", description=__doc__)
    sub = ap.add_subparsers(dest="orden", required=True)
    act = sub.add_parser("actualizar", help="descarga de nuevo las fuentes (necesita Internet)")
    act.add_argument("--fuente", action="append", choices=FUENTES)
    act.add_argument("--desde", type=date.fromisoformat, default=date(2021, 1, 1))
    act.add_argument("--hasta", type=date.fromisoformat, default=date.today())
    act.add_argument(
        "--sintetico", action="store_true", help="contingencia: genera datos sintéticos marcados"
    )
    act.add_argument("--directorio", type=Path, default=RUTA_SNAPSHOTS)
    ver = sub.add_parser("verificar", help="comprueba sha256 y contrato de cada instantánea")
    ver.add_argument("--directorio", type=Path, default=RUTA_SNAPSHOTS)
    a = ap.parse_args(argv)
    errores = 0
    if a.orden == "actualizar":
        for fuente in a.fuente or [f for f in FUENTES if f in DESCARGADORES]:
            try:
                _actualizar(fuente, a.desde, a.hasta, a.directorio, a.sintetico)
                print(f"OK {fuente}")
            except Exception as exc:  # se conserva la instantánea anterior
                errores += 1
                print(
                    f"ERROR {fuente}: {type(exc).__name__}: {exc}. "
                    "Se conserva la instantánea anterior.",
                    file=sys.stderr,
                )
    else:
        for fuente in leer_manifiesto(a.directorio):
            try:
                leer(fuente, a.directorio)
                print(f"OK {fuente}")
            except InstantaneaCorrupta as exc:
                errores += 1
                print(f"ERROR {exc}", file=sys.stderr)
    return 1 if errores else 0
