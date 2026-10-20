"""Festivos de España, Canarias y los mercados emisores (librería holidays) y vacaciones
escolares aproximadas."""

from __future__ import annotations

from datetime import date, timedelta

import holidays
import pandas as pd
from dateutil.easter import easter

# Fiestas insulares de Canarias (patronas de cada isla). Tenerife no tiene fiesta insular oficial:
# la Candelaria (2 feb) y el Cristo de La Laguna (14 sep) son locales de un municipio.
INSULARES = {
    "Gran Canaria": (9, 8, "Nuestra Señora del Pino"),
    "Lanzarote": (9, 15, "Nuestra Señora de los Volcanes"),
    "Fuerteventura": (9, 18, "Nuestra Señora de la Peña"),
}

PAISES = ("ES", "GB", "DE", "SE", "NO", "DK", "FI", "NL", "BE", "FR", "IE", "IT")


def _dias(desde: date, hasta: date, pais: str, nombre: str) -> list[dict]:
    return [
        {"fecha": desde + timedelta(d), "ambito": "escolar", "pais": pais, "nombre": nombre}
        for d in range((hasta - desde).days + 1)
    ]


def _semana_iso(anio: int, semana: int) -> tuple[date, date]:
    lunes = date.fromisocalendar(anio, semana, 1)
    return lunes - timedelta(days=2), lunes + timedelta(days=6)  # sábado anterior a domingo


def vacaciones_escolares(anio: int) -> pd.DataFrame:
    """Reglas aproximadas (no calendarios oficiales): Navidad, Semana Santa/Pascua y verano en
    todos; semana blanca nórdica (semana ISO 8: SE/NO/DK/FI); *half-term* británico (semanas 8,
    22 y 43); Carnaval en Canarias (ES; semana lectiva especial, no festivo); otoño en DE/NL/BE
    (semana 43)."""
    p = easter(anio)
    filas: list[dict] = []
    for pais in PAISES:
        filas += _dias(date(anio, 1, 1), date(anio, 1, 6), pais, "Vacaciones de Navidad")
        filas += _dias(date(anio, 12, 22), date(anio, 12, 31), pais, "Vacaciones de Navidad")
        filas += _dias(p - timedelta(days=7), p + timedelta(days=7), pais, "Vacaciones de Pascua")
        verano = (
            (date(anio, 6, 22), date(anio, 9, 8))
            if pais in ("ES", "IT")
            else (date(anio, 7, 20), date(anio, 8, 31))
        )
        filas += _dias(*verano, pais, "Vacaciones de verano")
    for pais in ("SE", "NO", "DK", "FI"):
        filas += _dias(*_semana_iso(anio, 8), pais, "Semana blanca")
    for semana in (8, 22, 43):
        filas += _dias(*_semana_iso(anio, semana), "GB", "Half-term")
    for pais in ("DE", "NL", "BE"):
        filas += _dias(*_semana_iso(anio, 43), pais, "Vacaciones de otoño")
    filas += _dias(
        p - timedelta(days=49), p - timedelta(days=45), "ES", "Semana de Carnaval (Canarias)"
    )
    return pd.DataFrame(filas).drop_duplicates(["fecha", "ambito", "pais"])


def generar(anios: range) -> pd.DataFrame:
    filas = []
    nacional_es = holidays.country_holidays("ES", years=anios)
    for d, n in nacional_es.items():
        filas.append({"fecha": d, "ambito": "nacional", "pais": "ES", "nombre": n})
    for d, n in holidays.country_holidays("ES", subdiv="CN", years=anios).items():
        if d not in nacional_es:
            filas.append({"fecha": d, "ambito": "autonomico", "pais": "ES", "nombre": n})
    for anio in anios:
        for isla, (mes, dia, nombre) in INSULARES.items():
            filas.append(
                {
                    "fecha": date(anio, mes, dia),
                    "ambito": f"insular:{isla}",
                    "pais": "ES",
                    "nombre": nombre,
                }
            )
    for pais in PAISES[1:]:
        # Suecia: sin los domingos que la librería cuenta como festivos por defecto.
        calendario = (
            holidays.SE(years=anios, include_sundays=False)
            if pais == "SE"
            else holidays.country_holidays(pais, years=anios)
        )
        for d, n in calendario.items():
            filas.append({"fecha": d, "ambito": "nacional", "pais": pais, "nombre": n})
    df = pd.concat(
        [pd.DataFrame(filas)] + [vacaciones_escolares(a) for a in anios], ignore_index=True
    )
    df["fecha"] = pd.to_datetime(df["fecha"]).dt.strftime("%Y-%m-%d")
    return df.groupby(["fecha", "ambito", "pais"], as_index=False)["nombre"].agg(
        lambda s: " / ".join(sorted(set(s)))
    )
