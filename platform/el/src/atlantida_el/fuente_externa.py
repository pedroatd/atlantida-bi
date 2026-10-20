"""Fuentes externas: instantáneas versionadas (ISTAC, AEMET, festivos, BCE) y el rate shopper.

Las instantáneas se vuelven a cargar enteras en cada ejecución (son pequeñas y su versión manda).
El rate shopper es un proveedor poco fiable: responde 503 de vez en cuando, le faltan días,
repite filas y cambió el formato de sus valores en algún momento. La carga reintenta, repasa
los últimos días por si llegan tarde, guarda los valores como texto tal como llegan (staging los
normaliza) y anota en meta.carga cuántas filas repetidas y huecos ha visto. Si no responde, se
registra el error y el resto de la carga sigue."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from datetime import date, datetime, timedelta

import dlt
import httpx
import pyarrow as pa
from atlantida_sources import contrato
from atlantida_sources.instantaneas import leer

from .esquema import COLUMNAS_CARGA

FUENTES_INSTANTANEA = ("istac_frontur", "aemet_diario", "festivos", "bce_tipos")
TABLAS_RATE_SHOPPER = ("compset_diario", "rate_shopper")
VENTANA_REPASO_DIAS = 7
TRAMO_MAXIMO_DIAS = 400
_TIPOS = {
    "periodo_mes": "text", "isla": "text", "pais_origen": "text", "llegadas": "bigint",
    "fecha": "date", "estacion": "text", "precipitacion": "double", "temperatura_maxima": "double",
    "ambito": "text", "pais": "text", "nombre": "text", "divisa": "text", "tipo_cambio": "double",
    "competidor": "text", "fecha_estancia": "date", "fecha_consulta": "date", "tarifa": "text",
    "hotel_id": "bigint", "ocupacion": "text", "adr": "text", "revpar": "text",
}  # fmt: skip
_COMO_TEXTO = {"compset_diario": ("ocupacion", "adr", "revpar"), "rate_shopper": ("tarifa",)}


class ProveedorNoDisponible(RuntimeError): ...


def hints_externos(fuente: str) -> dict[str, dict]:
    return {**{c: {"data_type": _TIPOS[c]} for c in contrato.columnas(fuente)}, **COLUMNAS_CARGA}


def _retry_after(r: httpx.Response) -> float:
    try:
        return min(max(float(r.headers.get("Retry-After", 0)), 0.0), 30.0)
    except ValueError:
        return 0.0


class ClienteRateShopper:
    def __init__(
        self,
        url: str,
        cliente: httpx.Client | None = None,
        reintentos: int = 4,
        espera: float = 0.5,
        dormir: Callable[[float], None] = time.sleep,
        token: str = "",
    ):
        self.url = url.rstrip("/")
        self._cabeceras = {"Authorization": f"Bearer {token}"} if token else {}
        self._c = cliente or httpx.Client(timeout=30)
        self.reintentos, self.espera, self._dormir = reintentos, espera, dormir

    def _get(self, ruta: str, params: dict | None = None):
        """GET con reintentos y espera exponencial. Todo fallo pasajero (error de red, 429, 5xx,
        JSON inválido) se reintenta y acaba en ProveedorNoDisponible; un 4xx que no se arregla
        reintentando se anota sin reintentar. Nunca aborta la carga entera."""
        motivo = ""
        for intento in range(self.reintentos + 1):
            pausa = 0.0
            try:
                r = self._c.get(f"{self.url}{ruta}", params=params, headers=self._cabeceras)
            except httpx.TransportError as exc:
                motivo = type(exc).__name__
            else:
                if r.status_code == 429 or r.status_code >= 500:
                    motivo = f"HTTP {r.status_code}"
                    pausa = _retry_after(r)
                elif r.status_code in (401, 403):
                    raise ProveedorNoDisponible(
                        "rate shopper: el token no es válido (RS_TOKEN o SIM_API_TOKEN en "
                        "platform/.env)"
                    )
                elif r.status_code >= 400:
                    raise ProveedorNoDisponible(
                        f"rate shopper {ruta} {params or ''}: respuesta HTTP {r.status_code}"
                    )
                else:
                    try:
                        return r.json()
                    except ValueError:
                        motivo = "respuesta no válida (JSON)"
            if intento < self.reintentos:
                self._dormir(max(self.espera * 2**intento, pausa))
        raise ProveedorNoDisponible(
            f"rate shopper {ruta} {params or ''}: sin respuesta tras {self.reintentos + 1} "
            f"intentos ({motivo})"
        )

    def corte(self) -> date | None:
        c = self._get("/salud").get("corte")
        return date.fromisoformat(c[:10]) if c else None

    def compset(self, desde: date, hasta: date) -> list[dict]:
        return self._get(
            "/compset_diario", {"desde": desde.isoformat(), "hasta": hasta.isoformat()}
        )

    def tarifas(self, fecha: date) -> list[dict]:
        return self._get("/rate_shopper", {"fecha_consulta": fecha.isoformat()})


_ARROW = {"text": pa.string(), "bigint": pa.int64(), "date": pa.date32(), "double": pa.float64()}


def _a_arrow(filas: list[dict], fuente: str, instante: datetime, origen: str) -> pa.Table:
    """Tabla Arrow con el esquema exacto del contrato (más _loaded_at y _origen): así dlt no añade
    _dlt_id ni _dlt_load_id y las tablas de raw_ext quedan con las columnas del contrato."""
    texto = _COMO_TEXTO.get(fuente, ())
    columnas = {}
    for c in contrato.columnas(fuente):
        valores = [f.get(c) for f in filas]
        if c in texto:
            valores = [None if v is None else str(v) for v in valores]
        elif _TIPOS[c] == "date":
            valores = [None if v is None else _a_fecha(v) for v in valores]
        columnas[c] = pa.array(valores, _ARROW[_TIPOS[c]])
    n = len(filas)
    columnas["_loaded_at"] = pa.array([instante] * n, pa.timestamp("us", tz="UTC"))
    columnas["_origen"] = pa.array([origen] * n, pa.string())
    esquema = pa.schema(
        [
            pa.field(k, v.type, nullable=k not in ("_loaded_at", "_origen"))
            for k, v in columnas.items()
        ]
    )
    return pa.table(columnas, schema=esquema)


def _a_fecha(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def _desde(estado: dict, desde_inicial: date) -> date:
    ultima = estado.get("ultima_fecha")
    if not ultima:
        return desde_inicial
    return max(desde_inicial, date.fromisoformat(ultima) - timedelta(days=VENTANA_REPASO_DIAS))


def _tramos(desde: date, hasta: date, dias: int) -> Iterator[tuple[date, date]]:
    ini = desde
    while ini <= hasta:
        fin = min(ini + timedelta(days=dias - 1), hasta)
        yield ini, fin
        ini = fin + timedelta(days=1)


def _contar(calidad: dict, filas: list[dict], claves: tuple[str, str], con_huecos: bool) -> None:
    vistas = [tuple(str(f[c]) for c in claves) for f in filas]
    unicas = set(vistas)
    calidad["filas"] = calidad.get("filas", 0) + len(vistas)
    calidad["repetidos"] = calidad.get("repetidos", 0) + len(vistas) - len(unicas)
    if con_huecos and unicas:
        fechas = sorted({date.fromisoformat(f[:10]) for _, f in unicas})
        dias = (fechas[-1] - fechas[0]).days + 1
        esperadas = len({e for e, _ in unicas}) * dias
        calidad["huecos"] = calidad.get("huecos", 0) + esperadas - len(unicas)
    calidad.setdefault("huecos", 0)


def _instantanea(nombre: str, instante: datetime):
    @dlt.resource(name=nombre, write_disposition="replace", columns=hints_externos(nombre))
    def leer_instantanea():
        df = leer(nombre)
        filas = df.astype(object).where(df.notna(), None).to_dict("records")
        yield _a_arrow(filas, nombre, instante, "instantanea")

    return leer_instantanea


def _compset(
    cliente: ClienteRateShopper, desde_inicial: date, hasta: date, instante: datetime, calidad: dict
):
    @dlt.resource(
        name="compset_diario",
        write_disposition="merge",
        primary_key=["hotel_id", "fecha"],
        columns=hints_externos("compset_diario"),
    )
    def leer_compset():
        estado = dlt.current.resource_state()
        for ini, fin in _tramos(_desde(estado, desde_inicial), hasta, TRAMO_MAXIMO_DIAS):
            try:
                filas = cliente.compset(ini, fin)
            except ProveedorNoDisponible as exc:
                calidad.setdefault("fallos", []).append(str(exc))
                return  # el estado no avanza: la próxima carga lo vuelve a pedir
            _contar(calidad, filas, ("hotel_id", "fecha"), con_huecos=True)
            if filas:
                yield _a_arrow(filas, "compset_diario", instante, "rate_shopper")
            estado["ultima_fecha"] = fin.isoformat()

    return leer_compset


def _tarifas(
    cliente: ClienteRateShopper, desde_inicial: date, hasta: date, instante: datetime, calidad: dict
):
    @dlt.resource(
        name="rate_shopper",
        write_disposition="merge",
        primary_key=["competidor", "fecha_estancia", "fecha_consulta"],
        columns=hints_externos("rate_shopper"),
    )
    def leer_tarifas():
        estado = dlt.current.resource_state()
        dia = _desde(estado, desde_inicial)
        while dia <= hasta:
            try:
                filas = cliente.tarifas(dia)
            except ProveedorNoDisponible as exc:
                calidad.setdefault("fallos", []).append(str(exc))
                return
            _contar(calidad, filas, ("competidor", "fecha_estancia"), con_huecos=False)
            if filas:
                yield _a_arrow(filas, "rate_shopper", instante, "rate_shopper")
            estado["ultima_fecha"] = dia.isoformat()
            dia += timedelta(days=1)

    return leer_tarifas


@dlt.source(name="externas", max_table_nesting=0)
def fuente_externa(
    cliente_rs: ClienteRateShopper | None,
    corte_rs: date | None,
    desde_inicial: date,
    tarifas_desde: date,
    instante: datetime,
    calidad: dict[str, dict],
):
    for nombre in FUENTES_INSTANTANEA:
        yield _instantanea(nombre, instante)
    if cliente_rs is not None and corte_rs is not None:
        # El informe del compset de un día se publica al día siguiente.
        yield _compset(
            cliente_rs,
            desde_inicial,
            corte_rs - timedelta(days=1),
            instante,
            calidad["compset_diario"],
        )
        # Las tarifas son una consulta por día (y muchas filas): se puede empezar más tarde.
        yield _tarifas(cliente_rs, tarifas_desde, corte_rs, instante, calidad["rate_shopper"])


_CLAVES = {
    "compset_diario": ("hotel_id", "fecha"),
    "rate_shopper": ("competidor", "fecha_estancia", "fecha_consulta"),
}


def definiciones_externas() -> dict[str, tuple[dict, str, tuple[str, ...]]]:
    defs = {n: (hints_externos(n), "replace", ()) for n in FUENTES_INSTANTANEA}
    defs |= {n: (hints_externos(n), "merge", _CLAVES[n]) for n in TABLAS_RATE_SHOPPER}
    return defs
