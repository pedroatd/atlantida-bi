"""Línea base de los objetivos (supuesto S10): el valor de cada KPI de sus criterios en el periodo
base, calculado en el almacén con las definiciones vigentes, y su escritura en atlantida.yml
(sin perder los comentarios del documento)."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import psycopg
from atlantida_def import cargar_definicion
from atlantida_def.simulacion import ESCALA_REFERENCIA, SEMILLA_REFERENCIA
from atlantida_el.config import ConfigEL
from atlantida_el.reloj_origen import RelojOrigen, leer_reloj_origen

DECIMALES = {"ratio": 4, "eur": 2, "puntos": 2, "dias": 1, "conteo": 0}


def calcular_linea_base(url_dwh: str) -> dict[str, dict[str, float]]:
    """Objetivo -> {kpi: valor} en el periodo base (cadena), redondeado según la unidad. Solo
    los objetivos con todos los KPI de sus criterios calculados: no se inventa ninguno."""
    d = cargar_definicion()
    unidades = {k.id: k.unidad for k in d.kpis}
    with psycopg.connect(url_dwh) as c:
        valores = dict(
            c.execute(
                "select kpi, valor from marts_kpi.kpi_periodo"
                " where periodo_id = %s and ambito = 'CADENA'",
                (str(d.periodo_base),),
            ).fetchall()
        )
    resultado = {}
    for o in d.objetivos:
        kpis = [c.kpi for c in o.criterios]
        if all(valores.get(k) is not None for k in kpis):
            resultado[o.id] = {k: round(float(valores[k]), DECIMALES[unidades[k]]) for k in kpis}
    return resultado


def clasificar(
    valores: dict[str, dict[str, float]], definicion=None
) -> tuple[dict[str, dict[str, float]], list[str], dict[str, list[tuple[str, float, float]]]]:
    """Compara lo calculado con el documento: (pendientes de fijar, ya fijadas e iguales,
    fijadas con valores distintos {objetivo: [(kpi, documento, calculado)]}). Igual quiere decir
    a menos de una unidad del último decimal de su unidad."""
    d = definicion or cargar_definicion()
    unidades = {k.id: k.unidad for k in d.kpis}
    fijadas = {o.id: o.linea_base for o in d.objetivos if o.linea_base is not None}
    pendientes, iguales, distintas = {}, [], {}
    for objetivo, kpis in valores.items():
        if objetivo not in fijadas:
            pendientes[objetivo] = kpis
            continue
        difieren = [
            (k, fijadas[objetivo].get(k), v)
            for k, v in kpis.items()
            if k not in fijadas[objetivo]
            or abs(fijadas[objetivo][k] - v) > 10 ** -DECIMALES[unidades[k]]
        ]
        if difieren:
            distintas[objetivo] = difieren
        else:
            iguales.append(objetivo)
    return pendientes, iguales, distintas


def problema_de_origen(reloj: RelojOrigen | None) -> str | None:
    """La línea base solo se fija con la simulación de referencia: escala 1 y semilla por
    defecto. Recibe el reloj del PMS de origen (atlantida_el.reloj_origen); devuelve el motivo
    para no escribir, o None."""
    if reloj is None:
        return "el PMS de origen no está sembrado (no hay reloj de la simulación)"
    if reloj.escala is None or reloj.semilla is None:
        return (
            "la API del profesor no informa de la escala ni de la semilla; la línea base del "
            "documento no se compara"
        )
    if reloj.escala != ESCALA_REFERENCIA or reloj.semilla != SEMILLA_REFERENCIA:
        return (
            f"el PMS de origen se sembró a escala {reloj.escala:g} con la semilla "
            f"{reloj.semilla}; la línea base se fija a escala {ESCALA_REFERENCIA:g} con la "
            f"semilla por defecto ({SEMILLA_REFERENCIA})"
        )
    return None


def origen_no_valido(config: ConfigEL) -> str | None:
    """problema_de_origen() del PMS que alimenta el almacén (sim.reloj o la API del profesor,
    según ORIGEN_PMS)."""
    return problema_de_origen(leer_reloj_origen(config))


def escribir_linea_base(
    valores: dict[str, dict[str, float]], ruta: Path, version: str, fecha: date, cambio: str
) -> None:
    """Rellena la línea base pendiente (null) de cada objetivo de «valores», sube la versión y
    añade la entrada del historial. Edita el texto (conserva los comentarios) y valida el
    resultado antes de escribirlo: si algo falla, el fichero no cambia."""
    texto = ruta.read_text(encoding="utf-8")
    for objetivo, kpis in valores.items():
        bloque = re.compile(rf"(  - id: {re.escape(objetivo)}\n(?:    .*\n)*?    linea_base: )null")
        mapa = "{" + ", ".join(f"{k}: {v!r}" for k, v in kpis.items()) + "}"
        texto, n = bloque.subn(lambda m, mapa=mapa: m.group(1) + mapa, texto, count=1)
        if n != 1:
            raise ValueError(f"no se encuentra la línea base pendiente de {objetivo}")
    texto, n = re.subn(r'^version: "[^"]+"', f'version: "{version}"', texto, count=1, flags=re.M)
    if n != 1:
        raise ValueError("no se encuentra la versión del documento")
    cambio_yaml = cambio.replace("\\", "\\\\").replace('"', '\\"')
    entrada = (
        f'    - {{version: "{version}", fecha: {fecha.isoformat()}, '
        f'cambio: "{cambio_yaml}", aprobado_por: direccion}}\n'
    )
    texto, n = re.subn(
        r"(  historial:\n(?:    - .*\n)+)", lambda m: m.group(1) + entrada, texto, count=1
    )
    if n != 1:
        raise ValueError("no se encuentra el historial del documento")
    provisional = ruta.with_name(f".{ruta.name}.nuevo")
    provisional.write_text(texto, encoding="utf-8")
    try:
        cargar_definicion(provisional)
        provisional.replace(ruta)
    finally:
        provisional.unlink(missing_ok=True)
