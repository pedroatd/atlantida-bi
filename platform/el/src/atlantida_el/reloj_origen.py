"""Reloj del PMS de origen (época, huella, corte, escala y semilla), del PMS local (sim.reloj, con
el rol pms_el) o de la API del profesor (GET /v1/salud). No importa el simulador: vale en la
edición del alumnado."""

from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import psycopg

from .config import ConfigEL
from .errores import FALTA_SIM_API_TOKEN, ApiNoDisponible, SinConexion

CANARIAS = ZoneInfo("Atlantic/Canary")


@dataclass(frozen=True)
class RelojOrigen:
    epoca: str
    huella: str
    corte: datetime  # hora local de Canarias, sin zona (como el simulador)
    escala: float | None
    semilla: int | None


def local_sin_zona(instante: datetime) -> datetime:
    """Como hace el simulador del PMS: una hora con zona pasa a la de Canarias y
    pierde la zona; una sin zona se toma ya como local."""
    return instante.astimezone(CANARIAS).replace(tzinfo=None) if instante.tzinfo else instante


def leer_reloj_pms(conn) -> RelojOrigen | None:
    if not conn.execute("select to_regclass('sim.reloj') is not null").fetchone()[0]:
        return None
    fila = conn.execute(
        "select corte, semilla, escala, huella, to_jsonb(r) ->> 'sembrado_en' "
        "from sim.reloj r where id = 1"
    ).fetchone()
    if fila is None:
        return None
    corte, semilla, escala, huella, epoca = fila
    return RelojOrigen(epoca or "", huella, local_sin_zona(corte), float(escala), int(semilla))


def leer_reloj_origen(
    config: ConfigEL, cliente_api: httpx.Client | None = None
) -> RelojOrigen | None:
    """El reloj del origen que dice ConfigEL (ORIGEN_PMS), o None si no está sembrado. Si no se
    puede leer, ErrorDeCarga (ApiNoDisponible o SinConexion) con un mensaje que dice qué hacer."""
    if config.origen == "api":
        return _reloj_api(config.api_url, config.api_token, cliente_api)
    try:
        with psycopg.connect(config.url_pms, connect_timeout=10) as c:
            return leer_reloj_pms(c)
    except psycopg.Error as exc:
        raise SinConexion(
            f"No se pudo leer el reloj del PMS de origen ({type(exc).__name__}): revisa que el "
            "PMS esté levantado y PMS_EL_USER/PMS_EL_PASSWORD en platform/.env."
        ) from exc


def _reloj_api(api_url: str, token: str, cliente_api: httpx.Client | None) -> RelojOrigen | None:
    # Sin ClienteCambios: fuente_api.py es el esqueleto del L3 en la edición del alumnado.
    # El proxy del profesor pide el token en todas las rutas, también en /salud.
    url = f"{api_url.rstrip('/')}/salud"
    cabeceras = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        with nullcontext(cliente_api) if cliente_api else httpx.Client(timeout=30) as c:
            r = c.get(url, headers=cabeceras)
        if r.status_code == 401:
            raise ApiNoDisponible(
                FALTA_SIM_API_TOKEN
                if not token
                else "La API del profesor rechaza el token: revisa SIM_API_TOKEN."
            )
        r.raise_for_status()
        s = r.json()
    except httpx.HTTPStatusError as exc:
        raise ApiNoDisponible(
            f"La API del profesor respondió HTTP {exc.response.status_code} a /salud: revisa "
            "SIM_API_URL (debe acabar en /v1) o espera a que el servicio vuelva."
        ) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise ApiNoDisponible(
            f"No se pudo leer el reloj de la API del profesor ({type(exc).__name__}): revisa "
            "SIM_API_URL y tu conexión."
        ) from exc
    if s.get("estado") != "ok":
        return None
    escala, semilla = s.get("escala"), s.get("semilla")
    return RelojOrigen(
        str(s.get("epoca") or s.get("huella")),
        s.get("huella") or "",
        local_sin_zona(datetime.fromisoformat(s["reloj"])),
        None if escala is None else float(escala),
        None if semilla is None else int(semilla),
    )
