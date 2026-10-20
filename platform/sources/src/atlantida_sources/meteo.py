"""Meteorología diaria por isla: AEMET OpenData (con clave) o, sin clave o si AEMET falla,
Open-Meteo (reanálisis ERA5) en las coordenadas de las mismas estaciones.

La clave de AEMET se lee solo del entorno y viaja en la cabecera ``api_key``: nunca en la URL
ni en los mensajes."""

from __future__ import annotations

import json
import math
import os
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import httpx
import pandas as pd

from . import red


@dataclass(frozen=True)
class Estacion:
    idema: str
    nombre: str
    isla: str
    lat: float
    lon: float


# Indicativos verificados contra el inventario de estaciones de AEMET.
ESTACIONES = {
    "Tenerife": Estacion("C429I", "Tenerife Sur Aeropuerto", "Tenerife", 28.0475, -16.5611),
    "Gran Canaria": Estacion("C649I", "Gran Canaria Aeropuerto", "Gran Canaria", 27.9289, -15.3892),
    "Lanzarote": Estacion("C029O", "Lanzarote Aeropuerto", "Lanzarote", 28.9519, -13.6000),
    "Fuerteventura": Estacion(
        "C249I", "Fuerteventura Aeropuerto", "Fuerteventura", 28.4447, -13.8633
    ),
}
URL_AEMET = (
    "https://opendata.aemet.es/opendata/api/valores/climatologicos/diarios/datos/"
    "fechaini/{ini}/fechafin/{fin}/estacion/{idema}"
)
URL_OPEN_METEO = "https://archive-api.open-meteo.com/v1/archive"
MESES_POR_PETICION = 6


def numero_aemet(valor: str | None) -> float:
    """AEMET usa coma decimal, «Ip» (precipitación inapreciable, < 0,1 mm) y «Acum» (acumulada)."""
    if valor is None or valor == "" or valor == "Acum":
        return math.nan
    if valor == "Ip":
        return 0.0
    return float(valor.replace(",", "."))


def decodificar_aemet(registros: list[dict], isla: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "fecha": [r["fecha"] for r in registros],
            "isla": isla,
            "estacion": [r["indicativo"] for r in registros],
            "precipitacion": [numero_aemet(r.get("prec")) for r in registros],
            "temperatura_maxima": [numero_aemet(r.get("tmax")) for r in registros],
        }
    )


def _trozos(desde: date, hasta: date):
    inicio = desde
    while inicio <= hasta:
        mes = inicio.month - 1 + MESES_POR_PETICION
        fin = min(date(inicio.year + mes // 12, mes % 12 + 1, 1) - timedelta(days=1), hasta)
        yield inicio, fin
        inicio = fin + timedelta(days=1)


ANTIGUEDAD_SIN_DATOS_DIAS = 365


def _leer_sin_datos(ruta: Path | None) -> set[tuple[str, str, str]]:
    if ruta is None or not ruta.is_file():
        return set()
    return {tuple(t) for t in json.loads(ruta.read_text(encoding="utf-8"))["tramos"]}


def _guardar_sin_datos(ruta: Path, tramos: set[tuple[str, str, str]]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + ".tmp")
    tmp.write_text(
        json.dumps({"tramos": sorted(list(t) for t in tramos)}, indent=1) + "\n",
        encoding="utf-8",
    )
    tmp.replace(ruta)


def descargar_aemet(
    clave: str,
    desde: date,
    hasta: date,
    cliente: httpx.Client | None = None,
    pausa: float = 1.5,
    parciales: Path | None = None,
    sin_datos: Path | None = None,
    hoy: date | None = None,
) -> pd.DataFrame:
    """`sin_datos`: JSON {"tramos": [[indicativo, inicio, fin], …]} con los tramos que AEMET
    respondió 404 y terminan hace más de ANTIGUEDAD_SIN_DATOS_DIAS días: no se vuelven a pedir.
    Un 404 reciente no se registra ni se guarda en `parciales` (puede llegar el dato más tarde)."""
    hoy = hoy or date.today()
    vacios = _leer_sin_datos(sin_datos)
    nuevos: set[tuple[str, str, str]] = set()
    cliente = cliente or httpx.Client(timeout=60)
    cab = {"api_key": clave, "Accept": "application/json"}
    partes = []
    for isla, est in ESTACIONES.items():
        for ini, fin in _trozos(desde, hasta):
            tramo = (est.idema, ini.isoformat(), fin.isoformat())
            if tramo in vacios:
                continue
            guardado = parciales / f"{est.idema}_{ini}_{fin}.json" if parciales else None
            if guardado is not None and guardado.is_file():
                registros = json.loads(guardado.read_text(encoding="utf-8"))
            else:
                url = URL_AEMET.format(
                    ini=f"{ini}T00:00:00UTC", fin=f"{fin}T23:59:59UTC", idema=est.idema
                )
                paso1 = red.get(cliente, url, headers=cab).json()
                if paso1.get("estado") == 404:  # «No hay datos que satisfagan esos criterios»
                    registros = []
                    if (hoy - fin).days > ANTIGUEDAD_SIN_DATOS_DIAS:
                        nuevos.add(tramo)
                    else:
                        guardado = None  # reciente: no se guarda; se volverá a pedir
                elif paso1.get("estado") != 200:  # AEMET devuelve los errores con HTTP 200
                    raise RuntimeError(
                        f"AEMET {est.idema} {ini}..{fin}: estado {paso1.get('estado')} "
                        f"({paso1.get('descripcion', 'sin descripción')})"
                    )
                else:
                    datos = red.get(cliente, paso1["datos"], headers={"Accept": "application/json"})
                    registros = json.loads(datos.content.decode("iso-8859-15"))
                if guardado is not None:
                    guardado.parent.mkdir(parents=True, exist_ok=True)
                    tmp = guardado.with_name(guardado.name + ".tmp")
                    tmp.write_text(json.dumps(registros, ensure_ascii=False), encoding="utf-8")
                    tmp.replace(guardado)
                time.sleep(pausa)
            if registros:
                partes.append(decodificar_aemet(registros, isla))
    if sin_datos is not None and nuevos:
        _guardar_sin_datos(sin_datos, vacios | nuevos)
    return pd.concat(partes, ignore_index=True)


def decodificar_open_meteo(doc: dict, est: Estacion) -> pd.DataFrame:
    d = doc["daily"]
    return pd.DataFrame(
        {
            "fecha": d["time"],
            "isla": est.isla,
            "estacion": f"OM-{est.idema}",
            "precipitacion": d["precipitation_sum"],
            "temperatura_maxima": d["temperature_2m_max"],
        }
    )


def descargar_open_meteo(
    desde: date, hasta: date, cliente: httpx.Client | None = None
) -> pd.DataFrame:
    cliente = cliente or httpx.Client(timeout=60)
    partes = []
    for est in ESTACIONES.values():
        r = red.get(
            cliente,
            URL_OPEN_METEO,
            params={
                "latitude": est.lat,
                "longitude": est.lon,
                "start_date": str(desde),
                "end_date": str(hasta),
                "daily": "precipitation_sum,temperature_2m_max",
                "timezone": "Atlantic/Canary",
            },
        )
        partes.append(decodificar_open_meteo(r.json(), est))
    return pd.concat(partes, ignore_index=True)


META_OPEN_METEO = {
    "url": URL_OPEN_METEO,
    "licencia": "CC BY 4.0",
    "atribucion": "Weather data by Open-Meteo.com (reanálisis ERA5, Copernicus)",
    "nota": "Sustituto de AEMET: rejilla ERA5 en las coordenadas de las estaciones de "
    "aeropuerto; estacion = OM-<indicativo AEMET>. Mismas columnas que aemet_diario.",
}


def descargar(
    desde: date,
    hasta: date,
    entorno: Mapping[str, str] = os.environ,
    cliente: httpx.Client | None = None,
    parciales: Path | None = None,
    sin_datos: Path | None = None,
) -> tuple[pd.DataFrame, dict]:
    clave = entorno.get("AEMET_API_KEY", "").strip()
    if clave:
        try:
            df = descargar_aemet(
                clave, desde, hasta, cliente, parciales=parciales, sin_datos=sin_datos
            )
            return df, {
                "url": URL_AEMET.split("/fechaini")[0],
                "licencia": "Condiciones de uso de AEMET OpenData",
                "atribucion": "© AEMET",
                "nota": "Valores climatológicos diarios; una estación de aeropuerto por isla.",
            }
        # Fallos esperables: red/HTTP, respuesta no válida (JSON, codificación, claves o
        # tipos inesperados), estado de AEMET o disco. Los errores de programación no se ocultan.
        except (
            httpx.HTTPError,
            RuntimeError,
            ValueError,
            KeyError,
            TypeError,
            OSError,
        ) as exc:  # mensaje saneado: nunca contiene la clave
            motivo = f"{type(exc).__name__}: {exc}".replace(clave, "***")
            print(f"AVISO: AEMET falló ({motivo}); se usa Open-Meteo.", file=sys.stderr)
            df = descargar_open_meteo(desde, hasta, cliente)
            return df, {
                **META_OPEN_METEO,
                "nota": f"AEMET falló ({motivo}). " + META_OPEN_METEO["nota"],
            }
    return descargar_open_meteo(desde, hasta, cliente), dict(META_OPEN_METEO)
