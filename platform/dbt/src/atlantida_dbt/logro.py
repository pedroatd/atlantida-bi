"""Comprobación cruzada: el índice de logro calculado en SQL (marts_kpi) es el mismo que da
atlantida_def.logro con los mismos valores (base, actual) de cada KPI.

Se compara criterio a criterio (magnitud, cumplimiento, progreso, base_cero) y objetivo a objetivo
(índice, semáforo, guardarraíles, logrado, KPI sin dato) en todas las evaluaciones (anual y
acumulado del año de cada mes) y ámbitos. Lo esperado sale solo de
``atlantida_def.evaluar_objetivo_parcial``, que con todos los datos es ``evaluar_objetivo`` y sin
alguno aplica la regla de datos incompletos de atlantida_def.
"""

from __future__ import annotations

from collections import defaultdict

import psycopg
from atlantida_def import cargar_definicion, evaluar_objetivo_parcial, ventanas_ytd
from atlantida_def.logro import TOLERANCIA
from atlantida_def.modelos import Objetivo, Semaforo
from psycopg.rows import dict_row

MESES = range(1, 13)


def _distintos(a: float | None, b: float | None, tolerancia: float) -> bool:
    if a is None or b is None:
        return (a is None) != (b is None)
    return abs(a - b) > tolerancia


def _comparar(
    o: Objetivo,
    umbrales: Semaforo,
    logro: dict,
    filas: dict[str, dict],
    clave: tuple,
    tolerancia: float,
    decimales_base: dict[str, int] | None = None,
) -> list[str]:
    errores: list[str] = []
    valores = {k: (f["base"], f["actual"]) for k, f in filas.items()}
    p = evaluar_objetivo_parcial(o, valores, umbrales)
    for orden, (c, det) in enumerate(zip(o.criterios, p.detalle, strict=True), 1):
        f = filas[c.kpi]
        donde = f"{clave} {c.kpi}"
        if f["orden"] != orden:
            errores.append(f"{donde}: orden SQL {f['orden']} y atlantida.yml {orden}")
        for campo in ("magnitud", "progreso"):
            if _distintos(f[campo], getattr(det, campo), tolerancia):
                errores.append(
                    f"{donde}: {campo} SQL {f[campo]} y atlantida_def {getattr(det, campo)}"
                )
        for campo in ("cumple", "base_cero"):
            if f[campo] != getattr(det, campo):
                errores.append(
                    f"{donde}: {campo} SQL {f[campo]} y atlantida_def {getattr(det, campo)}"
                )
    # El índice se compara con tolerancia: SQL redondea el texto decimal del double y Python, su
    # valor binario exacto (pueden diferir en 1e-12 en un empate de la decimotercera cifra).
    esperado = {
        "indice": p.indice,
        "semaforo": p.semaforo,
        "guardarrailes_ok": p.guardarrailes_ok,
        "logrado": p.logrado,
        "kpis_sin_dato": ", ".join(p.kpis_sin_dato) or None,
        # La madurez de los periodos es del almacén (int_periodos), no de la regla de logro.
        "datos_completos": not p.kpis_sin_dato and all(f["completo"] for f in filas.values()),
    }
    if _distintos(logro["indice"], esperado["indice"], tolerancia):
        errores.append(
            f"{clave}: índice SQL {logro['indice']} y atlantida_def {esperado['indice']}"
        )
    for campo, valor in esperado.items():
        if campo != "indice" and logro[campo] != valor:
            errores.append(f"{clave}: {campo} SQL {logro[campo]!r} y atlantida_def {valor!r}")

    objetivo_id, evaluacion, _mes, ambito = clave
    # La línea base del documento está redondeada a los decimales de su unidad: coincide si la
    # base del almacén está a menos de una unidad del último decimal (igual que linea-base).
    if (
        decimales_base is not None
        and o.linea_base is not None
        and (evaluacion, ambito) == ("anual", "CADENA")
    ):
        for kpi, valor in o.linea_base.items():
            base = filas[kpi]["base"]
            if base is None or abs(base - valor) > 10 ** -decimales_base[kpi]:
                errores.append(f"{clave} {kpi}: base SQL {base} y linea_base {valor}")
    return errores


def discrepancias(
    objetivos: dict[str, Objetivo],
    umbrales: Semaforo,
    logros: list[dict],
    criterios: list[dict],
    tolerancia: float = 1e-9,
    decimales_base: dict[str, int] | None = None,
) -> list[str]:
    """Diferencias entre las filas de objetivo_logro/objetivo_criterio y atlantida_def. Con
    decimales_base (KPI -> decimales de su unidad), también la base anual de la cadena frente a
    la línea base fijada en el documento; sin él (otra escala o semilla: S10), no."""
    por_clave: dict[tuple, dict[str, dict]] = defaultdict(dict)
    for f in criterios:
        por_clave[(f["objetivo_id"], f["evaluacion"], f["mes"], f["ambito"])][f["kpi"]] = f
    errores = [] if logros else ["objetivo_logro no tiene filas"]
    for logro in logros:
        clave = (logro["objetivo_id"], logro["evaluacion"], logro["mes"], logro["ambito"])
        o = objetivos.get(logro["objetivo_id"])
        if o is None:
            errores.append(f"{clave}: objetivo que no está en la definición")
            continue
        filas = por_clave.get(clave, {})
        if set(filas) != {c.kpi for c in o.criterios}:
            errores.append(
                f"{clave}: criterios SQL {sorted(filas)} y definición "
                f"{[c.kpi for c in o.criterios]}"
            )
            continue
        errores += _comparar(o, umbrales, logro, filas, clave, tolerancia, decimales_base)
    return errores


def comprobar_logro(url_dwh: str, tolerancia: float = 1e-9, linea_base: bool = True) -> list[str]:
    """Discrepancias entre marts_kpi y atlantida_def (lista vacía = idénticos): parámetros, ventanas
    del acumulado del año, filas esperadas y cada criterio y objetivo. Con linea_base, también la
    base de la cadena frente a la línea base del documento (solo tiene sentido si el almacén sale
    de la simulación de referencia: escala 1 y semilla por defecto)."""
    from .linea_base import DECIMALES

    d = cargar_definicion()
    decimales = {k.id: DECIMALES[k.unidad] for k in d.kpis} if linea_base else None
    objetivos = {o.id: o for o in d.objetivos}
    with psycopg.connect(url_dwh, row_factory=dict_row) as c:
        parametros = {
            f["clave"]: f["valor"]
            for f in c.execute("select clave, valor from staging.def_parametro").fetchall()
        }
        ytd = {
            f["periodo_id"]: (f["desde"], f["hasta"])
            for f in c.execute(
                "select periodo_id, desde, hasta from intermediate.int_periodos "
                "where tipo_periodo = 'ytd'"
            ).fetchall()
        }
        logros = c.execute("select * from marts_kpi.objetivo_logro").fetchall()
        criterios = c.execute("select * from marts_kpi.objetivo_criterio").fetchall()

    errores = []
    esperados = {
        "tolerancia": TOLERANCIA,
        "semaforo_verde": d.semaforo.verde,
        "semaforo_ambar": d.semaforo.ambar,
        "periodo_base": d.periodo_base,
        "periodo_evaluado": d.periodo_evaluado,
    }
    for k, v in esperados.items():
        if k not in parametros or float(parametros[k]) != v:
            errores.append(f"def_parametro.{k} = {parametros.get(k)} y atlantida_def {v}")
    for mes in MESES:
        actual, base = ventanas_ytd(d.periodo_evaluado, d.periodo_base, mes)
        for anio, ventana in ((d.periodo_evaluado, actual), (d.periodo_base, base)):
            periodo = f"{anio}-YTD-{mes:02d}"
            if ytd.get(periodo) != ventana:
                errores.append(f"{periodo}: SQL {ytd.get(periodo)} y ventanas_ytd {ventana}")

    evaluaciones = [("anual", None)] + [("ytd", m) for m in MESES]
    ambitos = {f["ambito"] for f in logros}
    claves = {(f["objetivo_id"], f["evaluacion"], f["mes"], f["ambito"]) for f in logros}
    esperadas = {(o, e, m, a) for o in objetivos for e, m in evaluaciones for a in ambitos}
    if claves != esperadas or len(claves) != len(logros) or "CADENA" not in ambitos:
        errores.append(
            f"objetivo_logro: {len(logros)} filas; faltan {sorted(esperadas - claves)[:5]}, "
            f"sobran {sorted(claves - esperadas, key=str)[:5]}"
        )
    return errores + discrepancias(objetivos, d.semaforo, logros, criterios, tolerancia, decimales)
