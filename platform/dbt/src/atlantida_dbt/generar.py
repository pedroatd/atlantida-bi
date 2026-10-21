"""Ficheros del proyecto dbt que se derivan de atlantida.yml. No se editan a mano: se regeneran
con `atlantida-dbt generar` y una prueba falla si están desactualizados."""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import yaml
from atlantida_def import cargar_definicion
from atlantida_def.formato import SEPARADOR_DECIMAL, SEPARADOR_MILES, decimales_kpi
from atlantida_def.logro import TOLERANCIA
from atlantida_def.modelos import MADUREZ_RESERVA_DIAS, parametros_rojo

from .formulas import formulas_kpi
from .rutas import PROYECTO

AVISO = (
    "Generado por `atlantida-dbt generar` a partir de platform/definicion/atlantida.yml: "
    "no editar a mano."
)
_MADUREZ = (
    "cuenta las reservas con su estado un mes después del periodo (madurez, S14): ese corte "
    "depende del periodo consultado y una métrica semántica no puede expresarlo"
)
FUERA_DE_LA_CAPA_SEMANTICA = {
    "pickup": "se mide en una fecha de corte (ventana de 7 días), no es una agregación por periodo",
    "dias_max_aspecto_en_rojo": (
        "necesita el enriquecimiento de reseñas por aspectos (módulo de IA)"
    ),
    "cac_reserva_neta": _MADUREZ,
    "cuota_directa_captacion": _MADUREZ,
    "estancia_media": _MADUREZ,
}


def _csv(cabecera: list[str], filas: list[list]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(cabecera)
    w.writerows(filas)
    return buf.getvalue()


DESPLIEGUE_SEMANTICO = {"costes_operativos": ("coste_total", "comisiones")}
"""Métricas base que en la capa semántica son la suma de otras (métrica derivada). En los KPI
se sustituyen por esa suma: MetricFlow rellena con 0 las métricas simples sin hechos
(fill_nulls_with), pero no las derivadas, y un hotel-día sin costes ni comisiones daría un GOPPAR
nulo en vez de numérico como en marts_kpi. El resultado es el mismo que la fórmula de marts_kpi."""


def _expr_semantica(expr: str) -> str:
    for metrica, sumandos in DESPLIEGUE_SEMANTICO.items():
        expr = re.sub(rf"\b{metrica}\b", "(" + " + ".join(sumandos) + ")", expr)
    return expr


def _metricas_semanticas(metricas: list[str]) -> list[str]:
    return [x for m in metricas for x in DESPLIEGUE_SEMANTICO.get(m, (m,))]


CAPA_SEMANTICA = "models/semantic"
"""Carpeta de la capa semántica (MetricFlow): la edición del alumnado la trae desde el L7."""

_HUERFANOS = (
    "macros/generado/*",
    "seeds/def_*.csv",
    "models/semantic/*_generado.yml",
    "models/marts/kpi/*_generado.yml",
)
"""Patrones de los ficheros que solo crea el generador: cualquier otro que case es un resto."""


DERIVADAS_BASE_DIARIA = {"costes_operativos": ("coste_total", "comisiones")}
"""Métricas base que kpi_base_diaria calcula como suma de otras aportaciones (como la capa
semántica: un día sin costes ni comisiones vale 0, no nulo)."""

FUERA_DE_LA_BASE_DIARIA = {
    "noches_captadas_ventana": "ventana móvil de 7 días por fecha de corte",
    "noches_canceladas_ventana": "ventana móvil de 7 días por fecha de corte",
}
"""Métricas aditivas que no se asignan a un único día (el pickup): fuera de kpi_base_diaria."""

CON_CIERRE_CONTABLE = frozenset({"costes_operativos", "coste_marketing_atribuido"})
"""Métricas que solo existen tras el cierre contable del mes: sus KPI son nulos si algún día del
filtro pertenece a un mes sin apuntes de coste. Más estricta que kpi_periodo, que solo anula un
periodo sin ningún apunte: en Superset un rango que cruce un mes abierto daría un GOPPAR
mezclado."""

_MOTIVO_SUPERSET = {
    "distintos": (
        "recuento de huéspedes distintos: no se suma entre días ni hoteles; se muestra desde "
        "marts_experiencia.exp_repeticion_mensual"
    ),
    "maximo": (
        "máximo de una racha de días en rojo: no se suma; se muestra desde "
        "marts_experiencia.exp_aspectos_diario"
    ),
    "publicado": (
        "media ponderada por el inventario de una cifra publicada por el compset: se reagregaría "
        "con sumas si kpi_base_diaria guardara el producto valor × inventario, y no lo guarda; "
        "se muestra desde marts_revenue.mv_rendimiento_mensual y rev_rendimiento_diario"
    ),
    "ventana": (
        "ventana móvil de 7 días por fecha de corte: se muestra desde marts_revenue.rev_pickup"
    ),
}
CORTE_ANUAL_SUPERSET = frozenset(k for k, v in FUERA_DE_LA_CAPA_SEMANTICA.items() if v is _MADUREZ)
"""KPI con reservas netas: kpi_base_diaria trae el corte de madurez del año, así que en Superset
un año coincide con la cifra oficial, pero un mes no es la serie mensual oficial (kpi_periodo).
Mismo nombre, mismo significado: su etiqueta lo dice y su descripción remite a kpi_periodo."""
_SUFIJO_CORTE_ANUAL = " (corte anual)"
_NOTA_CORTE_ANUAL = (
    " En Superset se calcula con el corte de madurez del año: un año coincide con la cifra "
    "oficial; la serie mensual oficial está en marts_kpi.kpi_periodo."
)
_FORMATO = {"ratio": ".1%", "eur": ",.2f", "dias": ".1f", "puntos": ".1f", "conteo": ",d"}


def columnas_base_diaria(d) -> list[str]:
    """Métricas base aditivas que kpi_base_diaria guarda como columnas (sin las derivadas)."""
    return [
        m.id
        for m in d.metricas_base
        if m.agregacion == "suma"
        and m.id not in FUERA_DE_LA_BASE_DIARIA
        and m.id not in DERIVADAS_BASE_DIARIA
    ]


def _semantica_superset(d, f: dict[str, str]) -> str:
    columnas = set(columnas_base_diaria(d)) | set(DERIVADAS_BASE_DIARIA)
    agregacion = {m.id: m.agregacion for m in d.metricas_base}
    metricas, fuera = [], {}
    for k in d.kpis:
        if not set(k.metricas) <= columnas:
            if set(k.metricas) & set(FUERA_DE_LA_BASE_DIARIA):
                fuera[k.id] = _MOTIVO_SUPERSET["ventana"]
            else:
                tipo = next(agregacion[m] for m in k.metricas if agregacion[m] != "suma")
                fuera[k.id] = _MOTIVO_SUPERSET[tipo]
            continue
        nombres = "|".join(sorted(k.metricas, key=len, reverse=True))
        expr = re.sub(rf"\b({nombres})\b", r"SUM(\1)", f[k.id])
        if set(k.metricas) & CON_CIERRE_CONTABLE:
            expr = f"CASE WHEN BOOL_AND(con_costes) THEN {expr} END"
        anual = k.id in CORTE_ANUAL_SUPERSET
        metricas.append(
            {
                "nombre": k.id,
                "etiqueta": k.nombre + (_SUFIJO_CORTE_ANUAL if anual else ""),
                "descripcion": k.definicion + (_NOTA_CORTE_ANUAL if anual else ""),
                "expresion": expr,
                "formato": _FORMATO[k.unidad],
                "unidad": k.unidad,
                "sentido": k.sentido,
            }
        )
    return f"# {AVISO}\n" + yaml.safe_dump(
        {
            "dataset": {"esquema": "marts_kpi", "tabla": "kpi_base_diaria"},
            "metricas": metricas,
            "fuera": fuera,
            # Todos los KPI (también los que no se reagregan con sumas) con su nombre y unidad:
            # construir.py formatea con ellos los valores de kpi_periodo como Dash (cifra).
            "kpis": [
                {
                    "nombre": k.id,
                    "etiqueta": k.nombre,
                    "unidad": k.unidad,
                    "decimales": decimales_kpi(k.unidad, k.formula),
                }
                for k in d.kpis
            ],
            # atlantida_def.formato: el mismo formato español que Dash
            "separadores": {"decimal": SEPARADOR_DECIMAL, "miles": SEPARADOR_MILES},
        },
        allow_unicode=True,
        sort_keys=False,
        width=100,
    )


def _doc_base_diaria(d) -> str:
    nombres = {m.id: m for m in d.metricas_base}
    columnas = [
        {"name": "fecha", "description": "Día (calendario)."},
        {
            "name": "hotel",
            "description": (
                "Código del hotel; '-1' para hechos sin hotel en la dimensión (no es un hotel)."
            ),
        },
        {"name": "isla", "description": "Isla del hotel."},
        {"name": "tipo_hotel", "description": "Tipología del hotel."},
        {
            "name": "con_costes",
            "description": (
                "Verdadero si el mes del día tiene cierre contable en ese hotel "
                "(GOPPAR y CAC solo entonces)."
            ),
        },
        *(
            {"name": c, "description": f"{nombres[c].nombre} ({nombres[c].unidad}); suma del día."}
            for c in [*columnas_base_diaria(d), *DERIVADAS_BASE_DIARIA]
        ),
    ]
    return f"# {AVISO}\n" + yaml.safe_dump(
        {
            "version": 2,
            "models": [
                {
                    "name": "kpi_base_diaria",
                    "description": (
                        "Métricas base aditivas de atlantida.yml por día y hotel, en los días con "
                        "ocupación registrada (sin días futuros), con las reservas netas leídas "
                        "en el corte de madurez de su año (como el scorecard: un año agregado "
                        "coincide con marts_kpi.kpi_periodo): la tabla sobre la que Superset "
                        "calcula los KPI con las métricas generadas "
                        "(platform/viz/superset/generado/semantica.yml)."
                    ),
                    "data_tests": [
                        {"unique": {"arguments": {"column_name": "hotel || '-' || fecha"}}}
                    ],
                    "columns": columnas,
                }
            ],
        },
        allow_unicode=True,
        sort_keys=False,
        width=100,
    )


def contenidos() -> dict[str, str]:
    d = cargar_definicion()
    desconocidos = set(FUERA_DE_LA_CAPA_SEMANTICA) - {k.id for k in d.kpis}
    if desconocidos:
        raise ValueError(
            f"FUERA_DE_LA_CAPA_SEMANTICA cita KPI que no existen: {sorted(desconocidos)}"
        )
    f = formulas_kpi()
    h = d.horizonte_simulado
    ids = [m.id for m in d.metricas_base]
    macro = (
        f"{{# {AVISO} #}}\n"
        f"{{% macro metricas_base_ids() %}}{{{{ return({ids!r}) }}}}{{% endmacro %}}\n\n"
        "{% macro formulas_kpi() %}{{ return({\n"
        + ",\n".join(f"  {k!r}: {v!r}" for k, v in f.items())
        + "\n}) }}{% endmacro %}\n"
    )
    parametros = {m.id: m.parametros for m in d.metricas_base if m.parametros}
    macro += (
        "\n{% macro parametros_metricas() %}{{ return(" + repr(parametros) + ") }}{% endmacro %}\n"
    )
    macro += (
        "\n{% macro metricas_base_diarias() %}{{ return("
        + repr(columnas_base_diaria(d))
        + ") }}{% endmacro %}\n"
    )
    salida = {
        "seeds/def_kpi.csv": _csv(
            [
                "kpi",
                "nombre",
                "unidad",
                "sentido",
                "propietario",
                "latencia",
                "formula",
                "formula_sql",
                "en_capa_semantica",
            ],
            [
                [
                    k.id,
                    k.nombre,
                    k.unidad,
                    k.sentido,
                    k.propietario,
                    k.latencia,
                    k.formula,
                    f[k.id],
                    str(k.id not in FUERA_DE_LA_CAPA_SEMANTICA).lower(),
                ]
                for k in d.kpis
            ],
        ),
        "seeds/def_objetivo.csv": _csv(
            ["objetivo_id", "verbo", "enunciado", "responsable"],
            [[o.id, o.verbo, o.enunciado, o.responsable] for o in d.objetivos],
        ),
        "seeds/def_criterio.csv": _csv(
            ["objetivo_id", "orden", "kpi", "papel", "peso", "tipo", "sentido", "meta"],
            [
                [
                    o.id,
                    i,
                    c.kpi,
                    c.papel,
                    "" if c.peso is None else c.peso,
                    c.comparacion.tipo,
                    c.comparacion.sentido,
                    c.comparacion.meta,
                ]
                for o in d.objetivos
                for i, c in enumerate(o.criterios, 1)
            ],
        ),
        "seeds/def_parametro.csv": _csv(
            ["clave", "valor"],
            [
                ["version_definicion", d.version],
                ["periodo_base", d.periodo_base],
                ["periodo_evaluado", d.periodo_evaluado],
                ["semaforo_verde", d.semaforo.verde],
                ["semaforo_ambar", d.semaforo.ambar],
                ["tolerancia", TOLERANCIA],
                ["madurez_dias", MADUREZ_RESERVA_DIAS],
                ["inicio_historico", h.inicio],
                ["fin_historico", h.fin],
                ["historia_huespedes_desde", h.historia_huespedes_desde],
                *(["rojo_" + k, v] for k, v in parametros_rojo(d).items()),
                *(
                    [f"accion_{a.id}_{k}", v]
                    for a in d.acciones
                    if a.regla_pms is not None and a.regla_pms.seleccion is not None
                    for k, v in a.regla_pms.seleccion.model_dump().items()
                ),
            ],
        ),
        "macros/generado/kpis.sql": macro,
        "models/marts/kpi/kpi_base_diaria_generado.yml": _doc_base_diaria(d),
        "models/semantic/kpis_generado.yml": f"# {AVISO}\n"
        + yaml.safe_dump(
            {
                "version": 2,
                "metrics": [
                    {
                        "name": k.id,
                        "label": k.nombre,
                        "description": k.definicion,
                        "type": "derived",
                        "type_params": {
                            "expr": _expr_semantica(f[k.id]),
                            "metrics": [{"name": m} for m in _metricas_semanticas(k.metricas)],
                        },
                    }
                    for k in d.kpis
                    if k.id not in FUERA_DE_LA_CAPA_SEMANTICA
                ],
            },
            allow_unicode=True,
            sort_keys=False,
            width=100,
        ),
    }
    if not (PROYECTO / CAPA_SEMANTICA).is_dir():
        # Edición del alumnado antes del L7: sin la capa semántica no se genera su YAML.
        salida = {r: v for r, v in salida.items() if not r.startswith(f"{CAPA_SEMANTICA}/")}
    return salida


DESTINO_VIZ = PROYECTO.parent / "viz" / "superset"
"""Destino de la capa semántica de Superset: el generador nunca escribe fuera del destino que
recibe (ni con rutas relativas con «..» desde el proyecto dbt)."""


def contenidos_viz() -> dict[str, str]:
    d = cargar_definicion()
    return {"generado/semantica.yml": _semantica_superset(d, formulas_kpi())}


def _escribir(destino: Path, contenido: dict[str, str]) -> list[Path]:
    escritos = []
    for ruta, texto in contenido.items():
        f = destino / ruta
        if not f.is_file() or f.read_text(encoding="utf-8") != texto:
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(texto, encoding="utf-8")
            escritos.append(f)
    return escritos


def generar(destino: Path = PROYECTO, destino_viz: Path | None = None) -> list[Path]:
    escritos = _escribir(destino, contenidos())
    if destino_viz is not None:
        escritos += _escribir(destino_viz, contenidos_viz())
    return escritos


def comprobar(destino: Path = PROYECTO, destino_viz: Path | None = None) -> list[str]:
    """Rutas desactualizadas: ficheros que faltan o difieren, y restos que el generador ya no
    produce (en macros/generado/, seeds/def_*.csv o *_generado.yml). Con destino_viz, también
    los de la capa de Superset (prefijados con «viz:»)."""
    esperado = contenidos()
    pendientes = [
        r
        for r, t in esperado.items()
        if not (destino / r).is_file() or (destino / r).read_text(encoding="utf-8") != t
    ]
    restos = {
        f.relative_to(destino).as_posix()
        for patron in _HUERFANOS
        for f in destino.glob(patron)
        if f.is_file()
    }
    viz = []
    if destino_viz is not None:
        viz = [
            f"viz:{r}"
            for r, t in contenidos_viz().items()
            if not (destino_viz / r).is_file() or (destino_viz / r).read_text(encoding="utf-8") != t
        ]
    return pendientes + sorted(restos - set(esperado)) + viz
