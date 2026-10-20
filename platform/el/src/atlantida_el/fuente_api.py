"""Esqueleto del laboratorio L3: el cargador dlt del PMS desde la API de cambios del profesor.

Lo que tienes que construir. Las funciones con `raise NotImplementedError("completa …")` son
los huecos; las pruebas que dicen cuándo están bien:

    uv run pytest platform/el/tests/test_fuente_api.py

Cuando pasen, `make -C platform el SOLO=pms REINICIAR=1` carga raw_pms desde la API y
`make -C platform el SOLO=pms` repetido solo trae lo nuevo. Cómo se configura la API (SIM_API_URL,
SIM_API_TOKEN): README.md (raíz del repositorio) y platform/el/README.md («Cargar desde la API del
profesor»).

El contrato de la API (todas las rutas bajo SIM_API_URL, que termina en /v1; todas, también
/salud, llevan la cabecera «Authorization: Bearer <token>»):

- GET /salud: {"estado": "ok" | "sin_sembrar", "reloj", "huella", "epoca", …}. El «reloj» es el
  instante hasta el que hay datos: una sincronización lo fija una vez, al empezar, como su corte.
  La «huella» y la «epoca» identifican la siembra del PMS: cambian cuando el profesor lo vuelve a
  sembrar, y el cursor las lleva dentro (por eso un cursor de otra siembra da 409).
- GET /tablas: una entrada por tabla, {"tabla", "columnas": [{"nombre", "tipo"}], "clave",
  "clave_con_nulos"}. «tipo» es el tipo de PostgreSQL de la columna (p. ej. numeric(10,2)).
- GET /cambios?tabla=…&limite=…[&hasta=…][&cursor=…]: una página de filas cambiadas,
  {"filas", "cursor", "hay_mas", "hasta"}. El cursor es opaco: no se interpreta, se guarda y se
  devuelve tal cual en la petición siguiente (la primera página va sin cursor). El parámetro
  «hasta» es opcional: con él, la API corta en el menor entre él y su reloj; sin él, en su reloj.
  En los dos casos la respuesta trae en «hasta» el corte que aplicó de verdad, y ese se repite en
  todas las páginas siguientes: es el corte común de la sincronización, y ninguna página trae
  cambios posteriores a él aunque el PMS siga cambiando. No es una foto a un instante: una fila
  que cambia después del corte deja de verse en esta sincronización y llega en la siguiente. Este
  módulo fija un corte para toda la sincronización (todas las tablas) y lo
  pide ya en la primera página. Se pide la página siguiente mientras «hay_mas» sea verdadero.
- Los valores llegan en JSON: las fechas y los instantes como texto ISO 8601 y los numeric como
  número o texto; se convierten a los tipos de «columnas» (los numeric, a decimales exactos).
- 401: el token no vale. 409: el profesor ha vuelto a sembrar el PMS y el cursor guardado ya no
  vale: hay que cargar desde cero. 429, 502, 503 y 504: se reintenta, respetando Retry-After.

Ya está resuelto lo que no es el objeto del laboratorio: las peticiones con reintentos y la
traducción de cada error de la API a su excepción (ClienteCambios._get) y la conversión de tipos
a Arrow (_esquema_arrow, _valor, _a_tabla). Te toca: las tres llamadas a la API (salud, corte y
tablas), la paginación con cursor y «hasta» (ClienteCambios.paginas), el recurso de dlt con
merge por la clave de la tabla y el cursor guardado en su estado (_recurso) y la fuente que reúne
un recurso por tabla (fuente_api). Mantén los nombres y las firmas: pipeline.py los usa."""

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
from .fuente_pms import con_columnas_de_carga  # noqa: F401 (la usa _recurso)

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
        """Estado del PMS servido: el cuerpo de GET /salud, que lleva el token como todas las
        rutas, con estado, reloj, huella y época. La época cambia en cada siembra."""
        raise NotImplementedError("completa ClienteCambios.salud: pide /salud con self._get")

    def corte(self) -> str:
        """El corte de una sincronización: el «reloj» de /salud (se fija una vez, al empezar). Si
        el PMS aún no está sembrado (estado distinto de «ok»), lanza ApiNoDisponible con un
        mensaje que lo diga."""
        raise NotImplementedError(
            "completa ClienteCambios.corte: mira el estado de self.salud() y devuelve su reloj"
        )

    def tablas(self) -> list[dict]:
        """Las tablas que sirve la API, con sus columnas, su clave y las columnas de la clave que
        admiten nulos: el cuerpo de GET /tablas."""
        raise NotImplementedError("completa ClienteCambios.tablas: pide /tablas con self._get")

    def paginas(
        self, tabla: str, cursor: str | None, hasta: str, limite: int = 5000
    ) -> Iterator[dict]:
        """Todas las páginas de cambios de «tabla» desde «cursor» (None: desde el principio),
        cada una como el cuerpo de GET /cambios (pídelo con self._get). La primera página ya pide
        el corte «hasta» de la sincronización; las siguientes repiten el «hasta» que devolvió la
        API (el corte aplicado). Para cuando «hay_mas» es falso. Si la API dice que hay más pero
        no avanza el cursor, o no termina en MAX_PAGINAS páginas, lanza ApiNoDisponible (sin eso,
        un fallo de la API colgaría la carga)."""
        raise NotImplementedError(
            "completa ClienteCambios.paginas: pide /cambios con tabla, limite, hasta y cursor, "
            "repite el «hasta» de la respuesta y sigue el cursor mientras hay_mas"
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
    """El recurso de dlt de la tabla «t» (se devuelve sin ejecutarlo), según el contrato:

    - nombre, disposición (t.disposicion) y columnas (t.hints()) de la tabla; con merge, por la
      clave de /tablas (t.clave), para que repetir una carga no duplique filas; con replace, sin
      clave (dlt haría NOT NULL las columnas de la clave, y en algunas tablas admite nulos);
    - lee las páginas de cliente.paginas con el corte «hasta», desde el cursor de la carga
      anterior (en merge; replace relee la tabla entera desde el principio, así que puede perder
      en esa carga las filas que cambien después del corte: llegan en la siguiente);
    - el cursor que se guarda es el de la última página leída, en el estado del recurso, que dlt
      solo conserva si la carga termina bien;
    - cada fila llega con las columnas de linaje _loaded_at (instante) y _origen ("api"), con
      los tipos de las columnas de la tabla: _a_tabla(filas, _esquema_arrow(t)) convierte las
      filas de una página en una tabla de Arrow, y con_columnas_de_carga(tabla, instante, "api")
      (de fuente_pms.py) le añade el linaje.

    Las piezas de dlt que hacen falta (el paso 4 del capítulo del L3 enlaza su documentación):
    el decorador @dlt.resource, con name, write_disposition, primary_key y columns; el estado del
    recurso, dlt.current.resource_state(), un diccionario que dlt guarda entre cargas (en su
    documentación, «State»); y que un recurso es una función generadora que entrega (yield) lo
    que se carga, aquí una tabla de Arrow por página con filas."""
    raise NotImplementedError(
        "completa _recurso: un @dlt.resource de la tabla con su disposición y su clave, que "
        "sigue el cursor guardado en el estado del recurso"
    )


@dlt.source(name="pms", max_table_nesting=0)
def fuente_api(
    cliente: ClienteCambios, tablas: dict[str, TablaOrigen], instante: datetime, hasta: str
):
    """La fuente de dlt del PMS: un recurso (_recurso) por cada tabla de «tablas», todos con el
    mismo instante de carga y el mismo corte «hasta»."""
    raise NotImplementedError("completa fuente_api: entrega (yield) el _recurso de cada tabla")
