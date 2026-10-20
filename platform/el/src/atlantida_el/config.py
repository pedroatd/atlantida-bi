"""Configuración de las cargas: conexiones al PMS y al DWH, origen del PMS y rate shopper.
Se lee del entorno (con make, de platform/.env); en el anfitrión valen los puertos publicados y
dentro de Compose los internos (PMS_PORT_INTERNO, DWH_PORT_INTERNO)."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import quote


def _url(usuario: str, clave: str, host: str, puerto: str, base: str) -> str:
    return (
        f"postgresql://{quote(usuario, safe='')}:{quote(clave, safe='')}"
        f"@{host}:{puerto}/{quote(base, safe='')}"
    )


def url_dwh_como(usuario: str, clave: str, entorno: Mapping[str, str] = os.environ) -> str:
    return (
        f"postgresql://{quote(usuario, safe='')}:{quote(clave, safe='')}@"
        f"{entorno.get('DWH_HOST', '127.0.0.1')}:"
        f"{entorno.get('DWH_PORT_INTERNO') or entorno.get('DWH_PORT') or '5434'}/"
        f"{quote(entorno.get('DWH_DB', 'dwh'), safe='')}"
    )


@dataclass(frozen=True)
class ConfigEL:
    url_pms: str = field(repr=False)
    url_dwh: str = field(repr=False)
    origen: Literal["pms", "api"] = "pms"
    api_url: str | None = None
    api_token: str = field(default="", repr=False)
    rate_shopper_url: str | None = "http://127.0.0.1:8001"
    rs_token: str = field(default="", repr=False)
    reintentos_rs: int = 4
    tarifas_desde: date | None = None
    dir_dlt: Path = Path(tempfile.gettempdir()) / "atlantida-dlt"
    variable_clave_pms: str = field(default="PMS_PASSWORD", repr=False)

    def __post_init__(self):
        if self.origen not in ("pms", "api"):
            raise ValueError(f"ORIGEN_PMS debe ser «pms» o «api», no {self.origen!r}")
        if self.origen == "api" and not self.api_url:
            raise ValueError(
                "ORIGEN_PMS=api necesita SIM_API_URL (la URL …/v1 que te dé el profesor)"
            )

    @classmethod
    def desde_entorno(cls, env: Mapping[str, str] = os.environ) -> ConfigEL:
        usuario_el = (env.get("PMS_EL_USER") or "").strip()
        pms = _url(
            usuario_el or env.get("PMS_USER") or "pms",
            env.get("PMS_EL_PASSWORD", "") if usuario_el else env.get("PMS_PASSWORD", ""),
            env.get("PMS_HOST") or "127.0.0.1",
            env.get("PMS_PORT_INTERNO") or env.get("PMS_PORT") or "5433",
            env.get("PMS_DB") or "pms",
        )
        dwh = _url(
            env.get("LOADER_USER") or "loader",
            env.get("LOADER_PASSWORD", ""),
            env.get("DWH_HOST") or "127.0.0.1",
            env.get("DWH_PORT_INTERNO") or env.get("DWH_PORT") or "5434",
            env.get("DWH_DB") or "dwh",
        )
        origen = (env.get("ORIGEN_PMS") or "pms").strip().lower()
        # Edición del alumnado (origen api): el rate shopper es el del profesor; sin su URL no hay
        # rate shopper (None). Con el simulador local, el de siempre en RS_PORT.
        rs_url = env.get("RS_URL") or (
            None if origen == "api" else f"http://127.0.0.1:{env.get('RS_PORT') or '8001'}"
        )
        rs_token = env.get("RS_TOKEN") or (env.get("SIM_API_TOKEN", "") if origen == "api" else "")
        return cls(
            url_pms=pms,
            url_dwh=dwh,
            origen=origen,
            api_url=(env.get("SIM_API_URL") or None),
            api_token=env.get("SIM_API_TOKEN", ""),
            rate_shopper_url=rs_url,
            rs_token=rs_token,
            reintentos_rs=int(env.get("RS_REINTENTOS") or 4),
            tarifas_desde=date.fromisoformat(env["RS_TARIFAS_DESDE"])
            if env.get("RS_TARIFAS_DESDE")
            else None,
            dir_dlt=Path(env.get("EL_DIR_DLT") or cls.dir_dlt),
            variable_clave_pms="PMS_EL_PASSWORD" if usuario_el else "PMS_PASSWORD",
        )
