"""Definición del sistema de BI de Atlántida Hoteles: fuente única de verdad.

Objetivos, actores, medidas, métricas base, KPI, acciones y hoteles se leen de
``atlantida.yml``; el esquema del PMS, de ``contrato_pms.yml``, y el de las fuentes
externas, de ``contrato_externo.yml``.
"""

from .alertas import dispara
from .carga import (
    cargar_contrato,
    cargar_contrato_externo,
    cargar_definicion,
    cargar_restricciones,
)
from .formato import decimales_kpi, numero_es
from .logro import (
    DetalleCriterio,
    DetalleParcial,
    ResultadoObjetivo,
    ResultadoParcial,
    cumple_guardarrail,
    evaluar_objetivo,
    evaluar_objetivo_parcial,
    progreso_criterio,
    ventanas_ytd,
)
from .modelos import Alerta, Definicion, SeleccionHuespedes, parametros_rojo

__all__ = [
    "Alerta",
    "Definicion",
    "DetalleCriterio",
    "DetalleParcial",
    "ResultadoObjetivo",
    "ResultadoParcial",
    "SeleccionHuespedes",
    "cargar_contrato",
    "cargar_contrato_externo",
    "cargar_definicion",
    "cargar_restricciones",
    "cumple_guardarrail",
    "decimales_kpi",
    "dispara",
    "evaluar_objetivo",
    "evaluar_objetivo_parcial",
    "numero_es",
    "parametros_rojo",
    "progreso_criterio",
    "ventanas_ytd",
]
