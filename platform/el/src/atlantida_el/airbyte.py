"""Airbyte como alternativa a dlt (perfil full), configurado como código: airbyte/conexiones.yml
describe el origen (PMS con CDC: publicación y ranura de replicación lógica), el destino (DWH,
esquema raw_pms_airbyte) y la conexión con las tablas del contrato. `aplicar` crea o actualiza
cada objeto por su nombre mediante la API pública de Airbyte: aplicarla dos veces
no duplica nada.

Con otra configuración (`atlantida-el airbyte aplicar --config FICHERO`, la parte opcional del L3
con laboratorio/l03/kit/airbyte.yml) la conexión declara sus propias tablas (conexion.tablas) y
el origen, dónde prepararlo (origen.preparar): no se leen las tablas del PMS."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path

import httpx
import psycopg
import yaml
from psycopg import sql
from psycopg.conninfo import make_conninfo

from .errores import ErrorDeCarga
from .esquema import TablaOrigen

_VARIABLE = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")
_ID = {"sources": "sourceId", "destinations": "destinationId", "connections": "connectionId"}


def ruta_conexiones() -> Path:
    empaquetada = files("atlantida_el") / "airbyte" / "conexiones.yml"
    if empaquetada.is_file():
        return Path(str(empaquetada))
    return Path(__file__).resolve().parents[2] / "airbyte" / "conexiones.yml"


def _sustituir(nodo, env: Mapping[str, str], faltan: set[str]):
    """Sustituye las variables sobre el árbol ya leído: comillas o barras no tocan el YAML."""
    if isinstance(nodo, str):
        faltan.update(v for v in _VARIABLE.findall(nodo) if not env.get(v))
        return _VARIABLE.sub(lambda m: env.get(m.group(1), ""), nodo)
    if isinstance(nodo, dict):
        return {k: _sustituir(v, env, faltan) for k, v in nodo.items()}
    if isinstance(nodo, list):
        return [_sustituir(v, env, faltan) for v in nodo]
    return nodo


def cargar_conexiones(env: Mapping[str, str] = os.environ, ruta: Path | None = None) -> dict:
    arbol = yaml.safe_load((ruta or ruta_conexiones()).read_text(encoding="utf-8"))
    faltan: set[str] = set()
    conf = _sustituir(arbol, env, faltan)
    if faltan:
        raise ErrorDeCarga(f"Faltan variables para configurar Airbyte: {', '.join(sorted(faltan))}")
    return conf


def flujos(tablas: dict[str, TablaOrigen]) -> list[dict]:
    resultado = []
    for t in tablas.values():
        if t.disposicion == "merge":
            resultado.append(
                {
                    "name": t.nombre,
                    "syncMode": "incremental_deduped_history",
                    "primaryKey": [[c] for c in t.clave],
                    "cursorField": ["updated_at"],
                }
            )
        else:
            resultado.append({"name": t.nombre, "syncMode": "full_refresh_overwrite"})
    return resultado


def flujos_de_config(conf: dict) -> list[dict]:
    """Los flujos de una configuración que declara sus tablas en conexion.tablas (cada una con
    «tabla» y, si la tiene, «clave» y «cursor»): con clave, incremental con deduplicación por
    ella (con CDC, el cursor lo pone Airbyte si no se declara); sin clave, se relee entera."""
    tablas = (conf.get("conexion") or {}).get("tablas")
    if not isinstance(tablas, list) or not tablas:
        raise ErrorDeCarga("La configuración de Airbyte no declara sus tablas (conexion.tablas).")
    resultado = []
    for t in tablas:
        if not isinstance(t, dict) or not isinstance(t.get("tabla"), str):
            raise ErrorDeCarga(f"conexion.tablas: cada tabla necesita «tabla» ({t!r})")
        clave = t.get("clave") or []
        if clave:
            flujo = {
                "name": t["tabla"],
                "syncMode": "incremental_deduped_history",
                "primaryKey": [[c] for c in clave],
            }
            if t.get("cursor"):
                flujo["cursorField"] = [t["cursor"]]
            resultado.append(flujo)
        else:
            resultado.append({"name": t["tabla"], "syncMode": "full_refresh_overwrite"})
    return resultado


def url_origen(conf: dict) -> str:
    """Conexión al origen para prepararlo (publicación y ranura) desde donde se ejecuta la orden:
    los datos de origen.configuracion, con el host y el puerto de origen.preparar si los da (el
    host que ve Airbyte no tiene por qué ser el que se ve desde el equipo)."""
    c = conf["origen"]["configuracion"]
    preparar = conf["origen"].get("preparar") or {}
    return make_conninfo(
        host=str(preparar.get("host") or c["host"]),
        port=str(preparar.get("port") or c["port"]),
        dbname=c["database"],
        user=c["username"],
        password=c["password"],
    )


def preparar_pms(url_pms: str, publicacion: str, ranura: str, tablas_cdc: list[str]) -> None:
    """Publicación solo de las tablas con clave primaria (las demás van por full refresh): una
    tabla sin clave ni replica identity en una publicación rechaza sus UPDATE y DELETE, y el
    reverse ETL escribe en rate_restriction. Si la publicación ya existe, se deja con las tablas
    de ahora (alter publication … set table): repetir la orden tras cambiar las tablas converge a
    lo declarado. La ranura se crea una vez y no depende de las tablas."""
    if not tablas_cdc:
        raise ErrorDeCarga(
            "Ninguna tabla va por CDC (incremental_deduped_history, con clave primaria): no hay "
            "nada que publicar. Declara en conexion.tablas la clave de las tablas que la tienen "
            "en el origen o, si dejas la captura de cambios, quita la ranura (make "
            "airbyte-quitar-ranura)."
        )
    tablas = sql.SQL(", ").join(sql.Identifier("public", t) for t in tablas_cdc)
    with psycopg.connect(url_pms, autocommit=True) as c:
        if c.execute("show wal_level").fetchone()[0] != "logical":
            raise ErrorDeCarga(
                "pms-db no tiene wal_level=logical: vuelve a levantarlo con make up."
            )
        existe = c.execute(
            "select 1 from pg_publication where pubname = %s", (publicacion,)
        ).fetchone()
        orden = (
            "alter publication {} set table {}" if existe else "create publication {} for table {}"
        )
        c.execute(sql.SQL(orden).format(sql.Identifier(publicacion), tablas))
        if not c.execute(
            "select 1 from pg_replication_slots where slot_name = %s", (ranura,)
        ).fetchone():
            c.execute("select pg_create_logical_replication_slot(%s, 'pgoutput')", (ranura,))


def quitar_ranura(url_pms: str, ranura: str) -> bool:
    """Una ranura sin consumidor retiene WAL y el disco del PMS crece: bórrala si dejas Airbyte."""
    with psycopg.connect(url_pms, autocommit=True) as c:
        if not c.execute(
            "select 1 from pg_replication_slots where slot_name = %s", (ranura,)
        ).fetchone():
            return False
        c.execute("select pg_drop_replication_slot(%s)", (ranura,))
        return True


class ClienteAirbyte:
    def __init__(
        self, url: str, client_id: str, client_secret: str, cliente: httpx.Client | None = None
    ):
        self.raiz = url.rstrip("/")
        self.base = f"{self.raiz}/api/public/v1"
        self._c = cliente or httpx.Client(timeout=60)
        self._credenciales = {"client_id": client_id, "client_secret": client_secret}
        self._token: str | None = None
        self._secretos: set[str] = {client_secret} - {""}

    def _cabeceras(self) -> dict[str, str]:
        if self._token is None:
            r = self._c.post(
                f"{self.raiz}/api/v1/applications/token",
                json={**self._credenciales, "grant_type": "client_credentials"},
            )
            if r.status_code != 200:
                raise ErrorDeCarga(
                    f"Airbyte rechaza las credenciales (HTTP {r.status_code}): revisa "
                    "AIRBYTE_CLIENT_ID y AIRBYTE_CLIENT_SECRET (abctl local credentials)."
                )
            self._token = r.json()["access_token"]
        return {"Authorization": f"Bearer {self._token}"}

    def _pedir(
        self, metodo: str, ruta: str, cuerpo: dict | None = None, params: dict | None = None
    ) -> dict:
        try:
            r = self._c.request(
                metodo, f"{self.base}{ruta}", json=cuerpo, params=params, headers=self._cabeceras()
            )
        except httpx.TransportError as exc:
            raise ErrorDeCarga(
                f"Airbyte no responde en {self.raiz} ({type(exc).__name__}): "
                "¿has ejecutado make airbyte-instalar?"
            ) from None
        if r.status_code >= 400:
            raise ErrorDeCarga(
                f"Airbyte respondió HTTP {r.status_code} a {metodo} {ruta}{self._detalle(r)}"
            )
        return r.json()

    def _detalle(self, r: httpx.Response) -> str:
        """Mensaje de validación de Airbyte (útil para depurar la configuración), sin secretos."""
        try:
            cuerpo = r.json()
            texto = (
                str(cuerpo.get("message") or cuerpo.get("detail") or "")
                if isinstance(cuerpo, dict)
                else ""
            )
        except ValueError:
            texto = ""
        for secreto in self._secretos:
            texto = texto.replace(secreto, "***")
        return f": {texto[:300]}" if texto else ""

    def _espacio(self) -> str:
        return self._pedir("GET", "/workspaces")["data"][0]["workspaceId"]

    def _crear_o_actualizar(self, tipo: str, espacio: str, cuerpo: dict) -> str:
        existentes = self._pedir("GET", f"/{tipo}", params={"workspaceIds": espacio})["data"]
        previo = next((o for o in existentes if o.get("name") == cuerpo["name"]), None)
        if previo is None:
            return self._pedir("POST", f"/{tipo}", cuerpo)[_ID[tipo]]
        cambios = {
            k: v for k, v in cuerpo.items() if k not in ("workspaceId", "sourceId", "destinationId")
        }
        self._pedir("PATCH", f"/{tipo}/{previo[_ID[tipo]]}", cambios)
        return previo[_ID[tipo]]

    def aplicar(self, conf: dict, flujos: list[dict]) -> dict[str, str]:
        for bloque in (conf["origen"]["configuracion"], conf["destino"]["configuracion"]):
            self._secretos.update(str(v) for k, v in bloque.items() if "password" in k and v)
        espacio = self._espacio()
        origen = self._crear_o_actualizar(
            "sources",
            espacio,
            {
                "name": conf["origen"]["nombre"],
                "workspaceId": espacio,
                "configuration": {"sourceType": "postgres", **conf["origen"]["configuracion"]},
            },
        )
        destino = self._crear_o_actualizar(
            "destinations",
            espacio,
            {
                "name": conf["destino"]["nombre"],
                "workspaceId": espacio,
                "configuration": {
                    "destinationType": "postgres",
                    **conf["destino"]["configuracion"],
                },
            },
        )
        conexion = self._crear_o_actualizar(
            "connections",
            espacio,
            {
                "name": conf["conexion"]["nombre"],
                "sourceId": origen,
                "destinationId": destino,
                "namespaceDefinition": "custom_format",
                "namespaceFormat": conf["conexion"]["espacio_nombres"],
                "schedule": {"scheduleType": "manual"},
                "configurations": {"streams": flujos},
            },
        )
        return {"origen": origen, "destino": destino, "conexion": conexion}

    def sincronizar(self, conexion_id: str) -> str:
        return str(
            self._pedir("POST", "/jobs", {"connectionId": conexion_id, "jobType": "sync"})["jobId"]
        )
