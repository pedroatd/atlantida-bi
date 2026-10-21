"""Origen «api»: carga incremental desde la API de cambios del PMS que publica el profesor
(atlantida-sim servir). Cada tabla se lee siguiendo un cursor opaco que la API devuelve en cada
página; dlt lo guarda en su estado (en el propio DWH) y la siguiente carga sigue desde ahí.

La API identifica cada siembra (huella y época): si el profesor vuelve a sembrar el PMS, el
cursor guardado ya no vale (409) y hay que cargar desde cero con --reiniciar."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from datetime import date, datetime
from decimal import Decimal

import dlt
import httpx
import pyarrow as pa

from .errores import ApiNoDisponible, ErrorDeCarga, ReinicioNecesario, TokenNoValido
from .esquema import TablaOrigen, tipo_dlt
from .fuente_pms import con_columnas_de_carga

MENSAJE_409 = (
    "El PMS del profesor se ha vuelto a sembrar y el cursor guardado ya no vale: hay que cargar "
    "desde cero (make -C platform el SOLO=pms REINICIAR=1 desde la raíz del repositorio, o "
    "atlantida-el cargar --solo pms --reiniciar)."
)
_REINTENTABLES = {429, 502, 503, 504}
_ESPERA_MAXIMA = 120.0  # tope de lo que se obedece de Retry-After
MAX_PAGINAS = 100_000


def _retry_after(r: httpx.Response) -> float:
    try:
        return min(max(float(r.headers.get("Retry-After", 0)), 0.0), _ESPERA_MAXIMA)
    except ValueError:
        return 0.0


def _detalle(r: httpx.Response) -> str:
    try:
        d = r.json().get("detail")
    except (ValueError, AttributeError):
        return ""
    return f" ({str(d)[:200]})" if d else ""


class ClienteCambios:
    def __init__(
        self,
        url: str,
        token: str = "",
        cliente: httpx.Client | None = None,
        reintentos: int = 5,
        espera: float = 1.0,
        dormir: Callable[[float], None] = time.sleep,
    ):
        self.url = url.rstrip("/")
        self._c = cliente or httpx.Client(timeout=60)
        self._cabeceras = {"Authorization": f"Bearer {token}"} if token else {}
        self.reintentos, self.espera, self._dormir = reintentos, espera, dormir

    def _get(self, ruta: str, params: dict | None = None):
        motivo = ""
        sin_conexion = False  # el último intento no tuvo respuesta (URL, DNS, certificado, red)
        pausa = 0.0
        for intento in range(self.reintentos + 1):
            try:
                r = self._c.get(f"{self.url}{ruta}", params=params, headers=self._cabeceras)
            except httpx.TransportError as exc:
                motivo, sin_conexion = type(exc).__name__, True
            else:
                sin_conexion = False
                if r.status_code == 409:
                    raise ReinicioNecesario(MENSAJE_409)
                if r.status_code == 401:
                    raise TokenNoValido("La API de cambios rechaza el token: revisa SIM_API_TOKEN.")
                if r.status_code in _REINTENTABLES:
                    motivo = f"HTTP {r.status_code}"
                    pausa = _retry_after(r)
                elif r.status_code >= 400:
                    raise ErrorDeCarga(
                        f"La API de cambios respondió HTTP {r.status_code} a {ruta}"
                        f"{_detalle(r)}. Revisa SIM_API_URL (debe acabar en /v1) y que el "
                        "profesor sirva esta versión."
                    )
                else:
                    return r.json()
            if intento < self.reintentos:
                self._dormir(max(self.espera * 2**intento, pausa))
        if sin_conexion:
            raise ApiNoDisponible(
                f"No se puede conectar con la API de cambios ({self.url}) tras "
                f"{self.reintentos + 1} intentos ({motivo}): revisa SIM_API_URL, que el nombre "
                "resuelva (DNS) y el certificado, y tu conexión; si todo está bien, pregunta al "
                "profesor."
            )
        raise ApiNoDisponible(
            f"El servidor del profesor no está disponible ({self.url}: {motivo} tras "
            f"{self.reintentos + 1} intentos): inténtalo en unos minutos o pregunta al profesor."
        )

    def salud(self) -> dict:
        """Estado del PMS servido (GET /v1/salud, que lleva el token como todas las rutas):
        estado, reloj, huella y época. El sensor de Dagster sigue el reloj; la época cambia en
        cada siembra."""
        return self._get("/salud")

    def corte(self) -> str:
        """Reloj del PMS servido: el corte de una sincronización (se fija una vez, al empezar)."""
        salud = self.salud()
        if salud.get("estado") != "ok":
            raise ApiNoDisponible("El PMS del profesor aún no está sembrado: inténtalo más tarde.")
        return salud["reloj"]

    def tablas(self) -> list[dict]:
        return self._get("/tablas")

    def paginas(
        self, tabla: str, cursor: str | None, hasta: str, limite: int = 5000
    ) -> Iterator[dict]:
        """Todas las páginas, también la primera sin cursor, con el mismo corte «hasta»: ninguna
        página trae cambios posteriores al corte aunque el vivo avance mientras se lee."""
        for _ in range(MAX_PAGINAS):
            params = {
                "tabla": tabla,
                "limite": limite,
                "hasta": hasta,
                **({"cursor": cursor} if cursor else {}),
            }
            cuerpo = self._get("/cambios", params)
            # El cursor no lleva el corte: se repite el que la API aplicó de verdad (min(pedido,
            # reloj)) para que todas las páginas compartan el mismo corte.
            hasta = cuerpo.get("hasta") or hasta
            yield cuerpo
            siguiente = cuerpo.get("cursor") or cursor
            if not cuerpo.get("hay_mas"):
                return
            if siguiente == cursor:
                raise ApiNoDisponible(
                    f"La API de cambios dice que hay más filas de {tabla} pero no avanza el "
                    "cursor: pregunta al profesor."
                )
            cursor = siguiente
        raise ApiNoDisponible(
            f"La API de cambios no termina de paginar {tabla} tras {MAX_PAGINAS} páginas."
        )


def _esquema_arrow(t: TablaOrigen) -> pa.Schema:
    """Tipos Arrow equivalentes a los que dlt recibe del origen pms (sql_database, backend
    pyarrow): así raw_pms queda con las mismas columnas, sin las _dlt_id/_dlt_load_id que dlt
    añade a las filas JSON."""
    campos = []
    for nombre, tipo_sql in t.columnas:
        h = tipo_dlt(tipo_sql)
        d = h["data_type"]
        if d == "bigint":
            tipo = pa.int64()
        elif d == "text":
            tipo = pa.string()
        elif d == "bool":
            tipo = pa.bool_()
        elif d == "date":
            tipo = pa.date32()
        elif d == "timestamp":
            tipo = pa.timestamp("us", tz="UTC")
        elif d == "double":
            tipo = pa.float64()
        else:
            tipo = pa.decimal128(h.get("precision", 38), h.get("scale", 9))
        campos.append(pa.field(nombre, tipo))
    return pa.schema(campos)


def _valor(v, tipo: pa.DataType):
    if v is None:
        return None
    if pa.types.is_date32(tipo):
        return date.fromisoformat(v)
    if pa.types.is_timestamp(tipo):
        return datetime.fromisoformat(v)
    if pa.types.is_decimal(tipo):
        return Decimal(str(v)).quantize(Decimal(1).scaleb(-tipo.scale))
    return v


def _a_tabla(filas: list[dict], esquema: pa.Schema) -> pa.Table:
    return pa.Table.from_pylist(
        [{c.name: _valor(f.get(c.name), c.type) for c in esquema} for f in filas], schema=esquema
    )


def _recurso(t: TablaOrigen, cliente: ClienteCambios, instante: datetime, hasta: str):
    incremental = t.disposicion == "merge"
    esquema = _esquema_arrow(t)

    @dlt.resource(
        name=t.nombre,
        write_disposition=t.disposicion,
        primary_key=list(t.clave) if incremental else None,
        columns=t.hints(),
    )
    def leer():
        estado = dlt.current.resource_state()
        cursor = estado.get("cursor") if incremental else None
        for pagina in cliente.paginas(t.nombre, cursor, hasta):
            filas = pagina.get("filas") or []
            if filas:
                yield con_columnas_de_carga(_a_tabla(filas, esquema), instante, "api")
            if incremental and pagina.get("cursor"):
                estado["cursor"] = pagina["cursor"]  # dlt solo lo guarda si la carga termina bien

    return leer


@dlt.source(name="pms", max_table_nesting=0)
def fuente_api(
    cliente: ClienteCambios, tablas: dict[str, TablaOrigen], instante: datetime, hasta: str
):
    for t in tablas.values():
        yield _recurso(t, cliente, instante, hasta)
