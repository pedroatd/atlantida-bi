"""Pruebas del cargador dlt del PMS desde la API de cambios (laboratorio L3).

Sin red ni base de datos: la API es un httpx.MockTransport que responde lo que cada prueba
prepara, y dlt solo extrae (no carga en ninguna base). Pasan cuando fuente_api.py está completo:

    uv run pytest platform/el/tests/test_fuente_api.py
"""

from datetime import UTC, datetime
from decimal import Decimal

import dlt
import httpx
import pyarrow as pa
import pytest
from atlantida_el.errores import ApiNoDisponible, ReinicioNecesario, TokenNoValido
from atlantida_el.esquema import TablaOrigen
from atlantida_el.fuente_api import ClienteCambios, fuente_api

URL = "http://api.invalid/v1"
INSTANTE = datetime(2031, 1, 1, tzinfo=UTC)
CORTE = "2031-01-01T12:00:00+00:00"
RESERVA = TablaOrigen(
    "reserva",
    (("reserva_id", "bigint"), ("importe", "numeric(10,2)"), ("updated_at", "timestamptz")),
    ("reserva_id",),
    (),
)
TARIFA = TablaOrigen(  # su clave admite nulos: se relee entera en cada carga
    "tarifa", (("hotel_id", "bigint"), ("fecha", "date")), ("hotel_id", "fecha"), ("fecha",)
)


def _cliente(responder, vistas: list | None = None, **kw) -> ClienteCambios:
    def manejar(peticion: httpx.Request) -> httpx.Response:
        if vistas is not None:
            vistas.append((peticion.url.path, dict(peticion.url.params)))
        return responder(peticion)

    http = httpx.Client(transport=httpx.MockTransport(manejar))
    return ClienteCambios(URL, "token-de-prueba", cliente=http, dormir=lambda _: None, **kw)


def _paginas(cuerpos: dict[str | None, dict]):
    """Una API de cambios que responde a cada cursor (None: sin cursor) con su página."""
    return lambda p: httpx.Response(200, json=cuerpos[p.url.params.get("cursor")])


# --- La API: salud, tablas y errores ---


def test_corte_es_el_reloj_de_salud():
    vistas = []
    salud = {"estado": "ok", "reloj": CORTE, "huella": "h", "epoca": 1}
    c = _cliente(lambda p: httpx.Response(200, json=salud), vistas)
    assert c.salud() == salud, "salud devuelve el cuerpo de GET /salud"
    assert c.corte() == CORTE, "el corte de una sincronización es el reloj de /salud"
    assert vistas[0][0] == "/v1/salud", "salud pide /salud"


def test_corte_sin_sembrar_explica():
    c = _cliente(lambda p: httpx.Response(200, json={"estado": "sin_sembrar", "reloj": None}))
    with pytest.raises(ApiNoDisponible, match="sembrado"):
        c.corte()


def test_tablas_lista_las_de_la_api():
    tablas = [{"tabla": "reserva", "columnas": [], "clave": ["reserva_id"], "clave_con_nulos": []}]
    vistas = []
    c = _cliente(lambda p: httpx.Response(200, json=tablas), vistas)
    assert c.tablas() == tablas, "tablas devuelve el cuerpo de GET /tablas"
    assert vistas[0][0] == "/v1/tablas"


def test_401_es_token_no_valido():
    c = _cliente(lambda p: httpx.Response(401, json={"detail": "token"}))
    with pytest.raises(TokenNoValido, match="SIM_API_TOKEN"):
        c.tablas()


def test_409_pide_cargar_desde_cero():
    c = _cliente(lambda p: httpx.Response(409, json={"detail": "resembrado"}))
    with pytest.raises(ReinicioNecesario, match="REINICIAR=1"):
        list(c.paginas("reserva", "cursor-viejo", CORTE))


def test_503_con_retry_after_se_reintenta():
    esperas = []
    respuestas = [
        httpx.Response(503, headers={"Retry-After": "7"}),
        httpx.Response(200, json=[]),
    ]
    http = httpx.Client(transport=httpx.MockTransport(lambda p: respuestas.pop(0)))
    c = ClienteCambios(URL, "t", cliente=http, dormir=esperas.append)
    assert c.tablas() == [], "tras el 503, el segundo intento responde"
    assert esperas == [7.0], "espera lo que dice Retry-After antes de reintentar"


# --- Paginación con cursor y corte ---


def test_pagina_hasta_que_no_hay_mas():
    cuerpos = {
        None: {"filas": [{"reserva_id": 1}], "cursor": "c1", "hay_mas": True, "hasta": CORTE},
        "c1": {"filas": [{"reserva_id": 2}], "cursor": "c2", "hay_mas": True, "hasta": CORTE},
        "c2": {"filas": [], "cursor": "c2", "hay_mas": False, "hasta": CORTE},
    }
    vistas = []
    leidas = list(_cliente(_paginas(cuerpos), vistas).paginas("reserva", None, CORTE))
    assert [p["filas"] for p in leidas] == [[{"reserva_id": 1}], [{"reserva_id": 2}], []], (
        "entrega todas las páginas, en orden, hasta la que dice hay_mas = false"
    )
    assert [v[1].get("cursor") for v in vistas] == [None, "c1", "c2"], (
        "la primera página va sin cursor; las siguientes, con el de la página anterior"
    )
    assert {v[0] for v in vistas} == {"/v1/cambios"} and {v[1]["tabla"] for v in vistas} == {
        "reserva"
    }, "pide /cambios con la tabla"


def test_sigue_desde_el_cursor_guardado():
    cuerpos = {"c7": {"filas": [], "cursor": "c7", "hay_mas": False, "hasta": CORTE}}
    vistas = []
    list(_cliente(_paginas(cuerpos), vistas).paginas("reserva", "c7", CORTE))
    assert vistas[0][1].get("cursor") == "c7", "empieza en el cursor que se le da"


def test_repite_en_todas_las_paginas_el_hasta_que_aplico_la_api():
    aplicado = "2031-01-01T11:00:00+00:00"  # la API aplica min(pedido, su reloj)
    reloj = "2031-01-01T13:00:00+00:00"  # el reloj de la API sigue avanzando: no es el corte
    pagina = {"hasta": aplicado, "reloj": reloj}
    cuerpos = {
        None: {"filas": [{"reserva_id": 1}], "cursor": "c1", "hay_mas": True, **pagina},
        "c1": {"filas": [{"reserva_id": 2}], "cursor": "c2", "hay_mas": True, **pagina},
        "c2": {"filas": [], "cursor": "c2", "hay_mas": False, **pagina},
    }
    vistas = []
    list(_cliente(_paginas(cuerpos), vistas).paginas("reserva", None, CORTE))
    assert [v[1].get("hasta") for v in vistas] == [CORTE, aplicado, aplicado], (
        "la primera página pide el corte; las siguientes repiten el «hasta» que devolvió la API "
        "(no su «reloj»)"
    )


def test_hay_mas_sin_avanzar_el_cursor_no_cuelga():
    cuerpos = {"c": {"filas": [], "cursor": "c", "hay_mas": True, "hasta": CORTE}}
    with pytest.raises(ApiNoDisponible):
        list(_cliente(_paginas(cuerpos)).paginas("reserva", "c", CORTE))


# --- El recurso de dlt: tipos, merge por la clave y cursor guardado ---


def _api_de_reservas(vistas: list):
    """Sin cursor, dos páginas con filas (cursor c1 y, la última, c2); desde cualquier otro
    cursor, una página vacía que no lo avanza (como la API: el cursor solo avanza con filas)."""

    def responder(p: httpx.Request) -> httpx.Response:
        cursor = p.url.params.get("cursor")
        if cursor is None:
            filas = [
                {"reserva_id": 1, "importe": "12.5", "updated_at": "2031-01-01T09:00:00+00:00"},
                {"reserva_id": 2, "importe": "80.25", "updated_at": "2031-01-01T10:00:00+00:00"},
            ]
            return httpx.Response(
                200, json={"filas": filas, "cursor": "c1", "hay_mas": True, "hasta": CORTE}
            )
        if cursor == "c1":
            filas = [{"reserva_id": 3, "importe": "7", "updated_at": "2031-01-01T11:00:00+00:00"}]
            return httpx.Response(
                200, json={"filas": filas, "cursor": "c2", "hay_mas": False, "hasta": CORTE}
            )
        return httpx.Response(200, json={"filas": [], "cursor": cursor, "hay_mas": False})

    return _cliente(responder, vistas)


def _api_de_tarifas(vistas: list):
    """Una tabla que se relee entera: responde siempre la misma página, con su cursor."""

    def responder(p: httpx.Request) -> httpx.Response:
        filas = [{"hotel_id": 1, "fecha": None}, {"hotel_id": 2, "fecha": "2031-01-02"}]
        return httpx.Response(
            200, json={"filas": filas, "cursor": "t1", "hay_mas": False, "hasta": CORTE}
        )

    return _cliente(responder, vistas)


def test_tipos_numericos_como_decimales():
    fuente = fuente_api(_api_de_reservas([]), {"reserva": RESERVA}, INSTANTE, CORTE)
    tabla = pa.concat_tables([t for t in fuente if isinstance(t, pa.Table)])
    assert pa.types.is_decimal(tabla.schema.field("importe").type), (
        "numeric(10,2) llega como decimal, no como número de coma flotante"
    )
    assert tabla.column("importe").to_pylist() == [
        Decimal("12.50"),
        Decimal("80.25"),
        Decimal("7.00"),
    ]
    assert tabla.column("_origen").to_pylist() == ["api"] * 3, "lleva el linaje de la carga"
    assert "_loaded_at" in tabla.column_names


def test_merge_por_la_clave_de_tablas_y_relectura_de_las_claves_con_nulos():
    fuente = fuente_api(
        _api_de_reservas([]), {"reserva": RESERVA, "tarifa": TARIFA}, INSTANTE, CORTE
    )
    reserva, tarifa = fuente.resources["reserva"], fuente.resources["tarifa"]
    assert reserva.write_disposition == "merge", "una tabla con clave sin nulos se fusiona"
    columnas = reserva.compute_table_schema()["columns"]
    assert [c for c, h in columnas.items() if h.get("primary_key")] == ["reserva_id"], (
        "la clave del merge es la que da /tablas"
    )
    assert tarifa.write_disposition == "replace", "una clave con nulos no casa en un merge"
    columnas = tarifa.compute_table_schema()["columns"]
    assert [c for c, h in columnas.items() if h.get("primary_key")] == [], (
        "una tabla replace no lleva primary_key: dlt haría NOT NULL sus columnas y la clave de "
        "tarifa admite nulos"
    )


def test_la_segunda_carga_sigue_desde_el_cursor(tmp_path):
    vistas = []
    cliente = _api_de_reservas(vistas)
    for _ in range(2):
        p = dlt.pipeline("prueba_fuente_api", pipelines_dir=str(tmp_path))
        p.extract(fuente_api(cliente, {"reserva": RESERVA}, INSTANTE, CORTE))
    assert [v[1].get("cursor") for v in vistas] == [None, "c1", "c2"], (
        "el cursor de la última página (c2, no el de la primera) se guarda en el estado de dlt "
        "y la carga siguiente empieza en él"
    )


def test_replace_relee_desde_el_principio_en_cada_carga(tmp_path):
    vistas = []
    cliente = _api_de_tarifas(vistas)
    for _ in range(2):
        p = dlt.pipeline("prueba_fuente_api_replace", pipelines_dir=str(tmp_path))
        p.extract(fuente_api(cliente, {"tarifa": TARIFA}, INSTANTE, CORTE))
    assert [v[1].get("cursor") for v in vistas] == [None, None], (
        "una tabla replace se sustituye entera: cada carga la lee desde el principio, sin el "
        "cursor de la carga anterior"
    )
