"""Cuándo salta una alerta (fuente única: la usan atlantida_accion y las pruebas). Misma
tolerancia que el índice de logro: un valor igual al umbral, salvo el ruido de coma flotante, no
salta. Un valor nulo (periodo sin dato), una referencia ausente (deterioro) o una muestra por
debajo de la mínima nunca saltan: sin medida suficiente no hay alerta."""

from __future__ import annotations

from collections.abc import Sequence

from .logro import TOLERANCIA
from .modelos import Alerta

KPI_DIARIOS = frozenset({"ocupacion", "adr", "revpar", "trevpar", "cuota_directa"})
"""KPI de marts_kpi.kpi_diario (los únicos con detector de anomalías)."""


def umbral_efectivo(alerta: Alerta, referencia: float | None = None) -> float | None:
    """El umbral con el que se compara el KPI: el fijo («umbral») o la referencia del mismo periodo
    del año anterior más (o menos) el margen («deterioro»); None si no hay con qué comparar."""
    if alerta.tipo == "umbral":
        return alerta.umbral
    if alerta.tipo == "deterioro" and referencia is not None:
        signo = 1 if alerta.sentido == "por_encima" else -1
        return referencia + signo * alerta.margen
    return None


def muestra_suficiente(alerta: Alerta, muestras: Sequence[float | None] | None) -> bool:
    """Todas las muestras (periodo y, en deterioro, referencia) llegan al mínimo declarado."""
    if alerta.muestra_minima is None:
        return True
    if not muestras:
        return False
    return all(n is not None and n >= alerta.muestra_minima.minimo for n in muestras)


def dispara(
    alerta: Alerta,
    valor: float | None,
    referencia: float | None = None,
    muestras: Sequence[float | None] | None = None,
    ignorar_muestra: bool = False,
) -> bool:
    """``ignorar_muestra`` solo sirve para probar la plataforma a escala reducida (CI), donde
    ningún mes llega a la muestra mínima: nunca para analizar."""
    if alerta.tipo == "anomalia" or valor is None:
        return False
    if not ignorar_muestra and not muestra_suficiente(alerta, muestras):
        return False
    u = umbral_efectivo(alerta, referencia)
    if u is None:
        return False
    if alerta.sentido == "por_encima":
        return valor > u + TOLERANCIA
    return valor < u - TOLERANCIA
