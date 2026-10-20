"""Índice de logro de un objetivo y su semáforo.

Para cada criterio se calcula la magnitud comparada ``x`` a partir del valor
del KPI en el periodo base (``base``) y en el evaluado (``actual``):

* ``variacion_relativa``: ``x = actual / base - 1`` (con ``base == 0`` se lanza
  ``ValueError``, porque la variación relativa no está definida);
* ``variacion_absoluta``: ``x = actual - base``;
* ``umbral``: ``x = actual``.

Un criterio **se cumple** si ``x >= meta`` (sentido ``al_menos``) o
``x <= meta`` (sentido ``como_maximo``), con una tolerancia absoluta
``TOLERANCIA`` (1e-9) a favor del cumplimiento: en coma flotante,
``97 / 100 - 1`` vale ``-0.030000000000000027`` y, sin tolerancia, un ADR que cae
exactamente un 3 % incumpliría «no caer más de un 3 %». La misma regla decide
cuándo el progreso de un principal es 1.

El **progreso** ``p`` de un criterio principal, entre 0 y 1, es:

* ``p = 1`` si el criterio se cumple (en todos los tipos);
* si no, en los umbrales, la fracción del camino recorrido desde la línea base
  hasta el umbral, ``clamp((actual - base) / (meta - base), 0, 1)``, salvo que
  el umbral no esté «por delante» de la base en el sentido pedido
  (``al_menos`` con ``meta <= base`` o ``como_maximo`` con ``meta >= base``):
  entonces la base ya cumplía y se ha retrocedido, y ``p = 0``;
* si no, en las variaciones, ``clamp(x / meta, 0, 1)``, salvo que la meta sea 0
  o su signo contradiga el sentido (``al_menos`` con meta negativa,
  ``como_maximo`` con meta positiva): entonces ``p = 0``. Con meta negativa y
  ``como_maximo`` (una reducción), el cociente de dos negativos mide la
  fracción recorrida.

Además, el modelo rechaza un criterio **principal** de variación cuya meta no
sea una mejora (``al_menos`` con ``meta <= 0`` o ``como_maximo`` con
``meta >= 0``); los guardarraíles sí admiten cualquier signo (por ejemplo,
«el ADR no cae más de un 3 %» es ``al_menos -0.03``).

El **índice de logro** es ``Σ peso · p`` sobre los criterios principales. Los
guardarraíles no suman: solo se comprueba si se cumplen. El **semáforo** es
verde si ``indice >= verde`` y todos los guardarraíles se cumplen; rojo si
``indice < ambar``; ámbar en otro caso. Un guardarraíl incumplido nunca da verde.

**Logrado** no es lo mismo que verde: un objetivo está *logrado* si su índice es 1 (todos
los criterios principales cumplen su meta) **y** se cumplen todos los guardarraíles; está
*verde* si el índice llega al umbral verde y se cumplen los guardarraíles. Todo objetivo
logrado está en verde, pero no al revés.

**Datos incompletos** (``evaluar_objetivo_parcial``): un criterio no tiene dato si le falta el
valor base o el actual (también en un umbral: el progreso necesita la base) o si es una variación
relativa sobre una base 0; su magnitud, cumplimiento y progreso quedan en ``None``. Del objetivo
solo se da lo que no depende de esos datos: se evalúa con cada combinación de los dos extremos de
cada dato que falta (cumple, con progreso 1, o incumple con progreso 0) y cada resultado (índice,
guardarraíles, semáforo, logrado) se da si coincide en todas; si no, es ``None`` (el semáforo,
``"sin_datos"``). Basta con los extremos: el semáforo y «logrado» crecen con el progreso de cada
principal y con el cumplimiento de cada guardarraíl, y un dato intermedio da un resultado entre
los de los extremos. Con todos los datos, el resultado es el de ``evaluar_objetivo``.

**Seguimiento mensual** (``seguimiento`` de la definición, ``ytd_vs_ytd_base``): cada mes
se evalúa el acumulado del año en curso hasta el cierre de ese mes frente al mismo tramo
del año base; ``ventanas_ytd`` devuelve las dos ventanas de fechas.
"""

from __future__ import annotations

import calendar
from collections.abc import Mapping
from datetime import date
from itertools import product
from typing import Literal

from pydantic import BaseModel

from .modelos import Criterio, Objetivo, Semaforo


class DetalleCriterio(BaseModel):
    kpi: str
    papel: Literal["principal", "guardarrail"]
    base: float
    actual: float
    magnitud: float
    cumple: bool
    peso: float | None
    progreso: float | None


class ResultadoObjetivo(BaseModel):
    objetivo: str
    indice: float
    semaforo: Literal["verde", "ambar", "rojo"]
    guardarrailes_ok: bool
    logrado: bool
    """Índice 1 (todos los principales cumplen) y todos los guardarraíles cumplidos."""
    detalle: list[DetalleCriterio]


TOLERANCIA = 1e-9
"""Holgura absoluta al comparar la magnitud con la meta (errores de redondeo)."""


def _clamp(v: float) -> float:
    return min(1.0, max(0.0, v))


def magnitud(c: Criterio, base: float, actual: float) -> float:
    """Magnitud ``x`` que se compara con la meta del criterio."""
    tipo = c.comparacion.tipo
    if tipo == "variacion_relativa":
        if base == 0:
            raise ValueError(f"línea base 0 en variación relativa: {c.kpi}")
        return actual / base - 1
    if tipo == "variacion_absoluta":
        return actual - base
    return actual


def cumple_criterio(c: Criterio, base: float, actual: float) -> bool:
    """``x >= meta - TOLERANCIA`` si el sentido es ``al_menos``; ``x <= meta + TOLERANCIA``
    si es ``como_maximo``."""
    return _cumple(c, magnitud(c, base, actual))


def _cumple(c: Criterio, x: float) -> bool:
    """Regla de cumplimiento sobre una magnitud ya calculada."""
    meta = c.comparacion.meta
    if c.comparacion.sentido == "al_menos":
        return x >= meta - TOLERANCIA
    return x <= meta + TOLERANCIA


def cumple_guardarrail(c: Criterio, base: float, actual: float) -> bool:
    """Indica si un guardarraíl se respeta (misma regla de cumplimiento)."""
    return cumple_criterio(c, base, actual)


def progreso_criterio(c: Criterio, base: float, actual: float) -> float:
    """Progreso entre 0 y 1 de un criterio hacia su meta (ver el módulo)."""
    return _progreso(c, base, actual, magnitud(c, base, actual))  # valida la base antes


def _progreso(c: Criterio, base: float, actual: float, x: float) -> float:
    """Progreso con la magnitud ``x`` ya calculada (se calcula una sola vez por criterio)."""
    meta = c.comparacion.meta
    al_menos = c.comparacion.sentido == "al_menos"
    if _cumple(c, x):
        return 1.0
    if c.comparacion.tipo == "umbral":
        if (al_menos and meta <= base) or (not al_menos and meta >= base):
            return 0.0
        return _clamp((actual - base) / (meta - base))
    if meta == 0 or (al_menos and meta < 0) or (not al_menos and meta > 0):
        return 0.0
    return _clamp(x / meta)


def evaluar_objetivo(
    o: Objetivo, valores: dict[str, tuple[float, float]], umbrales: Semaforo
) -> ResultadoObjetivo:
    """Evalúa un objetivo con ``valores[kpi] = (base, actual)`` y devuelve índice y semáforo."""
    detalle: list[DetalleCriterio] = []
    indice = 0.0
    guardarrailes_ok = True
    for c in o.criterios:
        if c.kpi not in valores:
            raise ValueError(f"objetivo {o.id}: falta el valor (base, actual) del KPI {c.kpi}")
        base, actual = valores[c.kpi]
        x = magnitud(c, base, actual)
        cumple = _cumple(c, x)
        progreso = None
        if c.papel == "principal":
            progreso = _progreso(c, base, actual, x)
            indice += c.peso * progreso
        elif not cumple:
            guardarrailes_ok = False
        detalle.append(
            DetalleCriterio(
                kpi=c.kpi,
                papel=c.papel,
                base=base,
                actual=actual,
                magnitud=x,
                cumple=cumple,
                peso=c.peso,
                progreso=progreso,
            )
        )
    indice = round(indice, 12)
    if indice >= umbrales.verde and guardarrailes_ok:
        semaforo = "verde"
    elif indice < umbrales.ambar:
        semaforo = "rojo"
    else:
        semaforo = "ambar"
    logrado = indice >= 1.0 and guardarrailes_ok
    return ResultadoObjetivo(
        objetivo=o.id,
        indice=indice,
        semaforo=semaforo,
        guardarrailes_ok=guardarrailes_ok,
        logrado=logrado,
        detalle=detalle,
    )


class DetalleParcial(BaseModel):
    kpi: str
    papel: Literal["principal", "guardarrail"]
    base: float | None
    actual: float | None
    magnitud: float | None
    cumple: bool | None
    peso: float | None
    progreso: float | None
    base_cero: bool
    """Variación relativa sobre una base 0 (no definida): el criterio queda sin dato."""


class ResultadoParcial(BaseModel):
    objetivo: str
    indice: float | None
    semaforo: Literal["verde", "ambar", "rojo", "sin_datos"]
    guardarrailes_ok: bool | None
    logrado: bool | None
    kpis_sin_dato: list[str]
    """KPI de los criterios sin dato, en el orden de los criterios."""
    detalle: list[DetalleParcial]


def completar(c: Criterio, cumple: bool) -> tuple[float, float]:
    """Valores (base, actual) de uno de los dos extremos de un dato que falta: si ``cumple``, la
    magnitud es la meta (progreso 1); si no, incumple con progreso 0."""
    meta = c.comparacion.meta
    tipo = c.comparacion.tipo
    if cumple:
        return (meta, meta) if tipo == "umbral" else (1.0, 1.0 + meta)
    holgura = 1.0 + abs(meta)
    al_menos = c.comparacion.sentido == "al_menos"
    x = meta - holgura if al_menos else meta + holgura
    if tipo == "umbral":
        return (meta + holgura if al_menos else meta - holgura), x
    return (0.0, x) if tipo == "variacion_absoluta" else (1.0, 1.0 + x)


def _unico(valores: set):
    return next(iter(valores)) if len(valores) == 1 else None


def evaluar_objetivo_parcial(
    o: Objetivo,
    valores: Mapping[str, tuple[float | None, float | None]],
    umbrales: Semaforo,
) -> ResultadoParcial:
    """Evalúa un objetivo aunque falten datos (ver «Datos incompletos» en el módulo): un KPI
    ausente de ``valores``, un ``None`` en la base o en el actual, o una variación relativa sobre
    una base 0 dejan el criterio sin dato, y del objetivo solo se da lo que no depende de él."""
    detalle: list[DetalleParcial] = []
    conocidos: dict[str, tuple[float, float]] = {}
    faltan: list[Criterio] = []
    for c in o.criterios:
        base, actual = valores.get(c.kpi, (None, None))
        cero = c.comparacion.tipo == "variacion_relativa" and base == 0
        x = cumple = progreso = None
        if base is None or actual is None or cero:
            faltan.append(c)
        else:
            conocidos[c.kpi] = (base, actual)
            x = magnitud(c, base, actual)
            cumple = _cumple(c, x)
            if c.papel == "principal":
                progreso = _progreso(c, base, actual, x)
        detalle.append(
            DetalleParcial(
                kpi=c.kpi,
                papel=c.papel,
                base=base,
                actual=actual,
                magnitud=x,
                cumple=cumple,
                peso=c.peso,
                progreso=progreso,
                base_cero=cero,
            )
        )
    resultados = []
    for extremos in product([True, False], repeat=len(faltan)):
        completos = dict(conocidos)
        completos.update({c.kpi: completar(c, e) for c, e in zip(faltan, extremos, strict=True)})
        resultados.append(evaluar_objetivo(o, completos, umbrales))
    return ResultadoParcial(
        objetivo=o.id,
        indice=_unico({r.indice for r in resultados}),
        semaforo=_unico({r.semaforo for r in resultados}) or "sin_datos",
        guardarrailes_ok=_unico({r.guardarrailes_ok for r in resultados}),
        logrado=_unico({r.logrado for r in resultados}),
        kpis_sin_dato=[c.kpi for c in faltan],
        detalle=detalle,
    )


def ventanas_ytd(
    periodo_evaluado: int, periodo_base: int, mes: int
) -> tuple[tuple[date, date], tuple[date, date]]:
    """Ventanas del seguimiento mensual: acumulado del año evaluado hasta el cierre de ``mes``
    y el mismo tramo del año base, como ``((inicio, fin), (inicio_base, fin_base))``.

    Se compara mes cerrado con mes cerrado: en un año bisiesto, febrero llega al día 29.
    """
    if not 1 <= mes <= 12:
        raise ValueError(f"mes fuera de rango: {mes}")

    def tramo(anio: int) -> tuple[date, date]:
        return date(anio, 1, 1), date(anio, mes, calendar.monthrange(anio, mes)[1])

    return tramo(periodo_evaluado), tramo(periodo_base)
