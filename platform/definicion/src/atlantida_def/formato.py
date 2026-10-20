"""Formato español de las cifras de Atlántida, el mismo en Dash y en Superset: coma decimal y
punto de miles (convención española), y los decimales de cada KPI según su unidad. Dash lo usa
directamente; Superset lo recibe en generado/semantica.yml («atlantida-dbt generar») y en
D3_FORMAT de superset_config.py (una prueba comprueba que no divergen)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

SEPARADOR_DECIMAL = ","
SEPARADOR_MILES = "."
# Decimales por unidad: proporciones en % con uno, euros con dos, puntos con uno; los días y los
# recuentos enteros sin decimales.
DECIMALES_UNIDAD = {"ratio": 1, "eur": 2, "puntos": 1, "dias": 0, "conteo": 0}


def redondear(x: float, decimales: int) -> Decimal:
    """Redondeo comercial (0,25 → 0,3), el de PostgreSQL con to_char: el mismo texto en Dash y en
    Superset (round() de Python redondea al par: 0,25 → 0,2). Sin «-0»."""
    d = Decimal(repr(float(x))).quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)
    return abs(d) if d == 0 else d


def numero_es(x: float, decimales: int = 2) -> str:
    """1234.5 → «1.234,50» (con decimales=2)."""
    texto = f"{redondear(x, decimales):,.{decimales}f}"
    return texto.translate(str.maketrans({",": SEPARADOR_MILES, ".": SEPARADOR_DECIMAL}))


def decimales_kpi(unidad: str, formula: str = "") -> int:
    """Decimales con que se muestra un KPI. Un KPI de días o de recuento que es un cociente (una
    media, como la estancia media o la antelación media) lleva uno; los enteros, ninguno."""
    if unidad in ("dias", "conteo") and "/" in formula:
        return 1
    return DECIMALES_UNIDAD.get(unidad, 2)


_UNIDAD_ESCRITA = {"eur": "€", "dias": "días", "puntos": "puntos", "conteo": ""}


def unidad_comparacion(tipo: str, unidad: str) -> str:
    """Unidad en que se lee una cifra de una comparación de atlantida.yml: las variaciones
    relativas en %; las proporciones en % (niveles) o en puntos porcentuales (variaciones
    absolutas); el resto, en la unidad del KPI (€, días, puntos)."""
    if tipo == "variacion_relativa":
        return "%"
    if unidad == "ratio":
        return "p. p." if tipo == "variacion_absoluta" else "%"
    return _UNIDAD_ESCRITA.get(unidad, "")


def cifra_comparacion(
    x: float | None,
    tipo: str,
    unidad: str,
    con_signo: bool = False,
    decimales: int | None = None,
) -> str | None:
    """Cifra de una comparación con su unidad escrita (formato español): «-8,4 p. p.», «+57,4 %»,
    «42 días», «-2,3 puntos». Las proporciones y variaciones relativas, en % con un decimal; el
    resto, con los decimales de la unidad del KPI (``decimales`` para las medias). None sin dato."""
    if x is None:
        return None
    x = float(x)
    if tipo == "variacion_relativa" or unidad == "ratio":
        dec, valor = 1, 100 * x
    else:
        dec = decimales if decimales is not None else DECIMALES_UNIDAD.get(unidad, 2)
        valor = x
    valor = redondear(valor, dec)
    signo = "+" if con_signo and valor >= 0 else ""
    u = unidad_comparacion(tipo, unidad)
    return f"{signo}{numero_es(valor, dec)}{' ' + u if u else ''}"
