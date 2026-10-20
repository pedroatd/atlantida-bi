"""Modelo del documento de definición de un sistema de BI.

Cada clase corresponde a un bloque del documento de definición (capítulo 3):
objetivos con criterios de éxito compuestos, actores, medidas raw, métricas
base, KPI y acciones, más el gobierno (responsables, propietarios, control del
documento), el calendario de las acciones, el seguimiento y los supuestos.
``Definicion`` comprueba la integridad referencial: cada identificador citado existe y
ningún identificador se repite. El contraste con los contratos del PMS y de las fuentes
externas lo hace ``carga.validar_contra_contrato``.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FUNCIONES_FORMULA = frozenset({"max"})
"""Funciones que pueden aparecer en la fórmula de un KPI, además de las métricas base."""

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


class _Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Actor(_Modelo):
    id: str
    nombre: str
    nivel: Literal["estrategico", "tactico", "operativo", "soporte"]
    frecuencia: Literal["diaria", "semanal", "mensual", "continua"]
    necesidad: str
    kpis: list[str]


class MedidaRaw(_Modelo):
    id: str
    fuente: Literal["pms", "externa"]
    tabla: str
    columna: str
    descripcion: str
    grano: str
    """``fuente: externa``: ``tabla`` es una fuente de ``contrato_externo.yml`` y ``columna``,
    una de sus columnas (lo comprueba ``carga.validar_contra_contrato``)."""


class MetricaBase(_Modelo):
    id: str
    nombre: str
    formula: str
    medidas: list[str]
    unidad: str
    agregacion: Literal["suma", "distintos", "maximo", "publicado"]
    """Cómo se agrega entre hoteles y periodos: ``suma`` (aditiva), ``distintos`` (recuento de
    entidades distintas: se recalcula, no se suma), ``maximo`` (se toma el máximo) o
    ``publicado`` (valor de un informe externo: se usa tal cual o se pondera)."""
    descripcion: str | None = None
    """Aclaración opcional para el alumnado (convenciones, supuestos, alternativas)."""
    nota_docente: str | None = None
    """Nota para el libro (dónde se estudia o construye); el documento de la organización no la
    muestra."""
    parametros: dict[str, float | int | str] | None = None
    """Parámetros del cálculo que forman parte de la definición (cambiarlos cambia el valor del
    KPI). Hoy solo los tiene el semáforo de aspectos (``PARAMETROS_ROJO``)."""

    @model_validator(mode="after")
    def _parametros_obligatorios(self) -> MetricaBase:
        if self.id == "dias_aspecto_en_rojo" and set(self.parametros or {}) != PARAMETROS_ROJO:
            raise ValueError(
                f"métrica base {self.id}: parametros debe tener exactamente las claves "
                f"{sorted(PARAMETROS_ROJO)}"
            )
        return self


PARAMETROS_ROJO = frozenset(
    {"ventana_dias", "umbral", "menciones_min", "hueco_max_dias", "modelo", "version_modelo"}
)
"""Claves de los parámetros del semáforo de aspectos (métrica base ``dias_aspecto_en_rojo``)."""


def parametros_rojo(d: Definicion | None = None) -> dict:
    """Parámetros del semáforo de aspectos (métrica base dias_aspecto_en_rojo)."""
    from .carga import cargar_definicion

    d = d or cargar_definicion()
    return dict(next(m for m in d.metricas_base if m.id == "dias_aspecto_en_rojo").parametros)


class Kpi(_Modelo):
    id: str
    nombre: str
    definicion: str
    formula: str
    metricas: list[str]
    unidad: Literal["ratio", "eur", "dias", "puntos", "conteo"]
    sentido: Literal["subir", "bajar", "neutro"]
    """``neutro``: indicador de diagnóstico; no puede ser criterio principal de un objetivo."""
    actores: list[str]
    """Actores que consultan el KPI (consumidores)."""
    propietario: str
    """Actor de negocio que responde de la definición y del resultado del KPI; debe ser uno de
    sus ``actores``. El equipo de datos custodia el cálculo, pero no es propietario."""
    latencia: str = Field(min_length=1)
    """Cuándo está disponible el dato para decidir (p. ej. «D-1, a las 07:00» o «mensual,
    cerrado»)."""

    @model_validator(mode="after")
    def _formula_usa_sus_metricas(self) -> Kpi:
        usados = set(_IDENT.findall(self.formula)) - FUNCIONES_FORMULA
        if usados != set(self.metricas):
            raise ValueError(
                f"KPI {self.id}: la fórmula usa {sorted(usados)} "
                f"pero declara las métricas {sorted(self.metricas)}"
            )
        return self


class Comparacion(_Modelo):
    tipo: Literal["variacion_relativa", "variacion_absoluta", "umbral"]
    sentido: Literal["al_menos", "como_maximo"]
    meta: float


class Criterio(_Modelo):
    kpi: str
    papel: Literal["principal", "guardarrail"]
    comparacion: Comparacion
    peso: float | None = None

    @model_validator(mode="after")
    def _peso_segun_papel(self) -> Criterio:
        if self.papel == "principal":
            if self.peso is None:
                raise ValueError(f"criterio principal {self.kpi}: falta el peso")
            if not 0 < self.peso <= 1:
                raise ValueError(f"criterio principal {self.kpi}: el peso debe estar en (0, 1]")
        elif self.peso is not None:
            raise ValueError(f"guardarraíl {self.kpi}: un guardarraíl no lleva peso")
        return self


class Objetivo(_Modelo):
    id: str
    verbo: str
    enunciado: str
    responsable: str
    """Actor que responde del objetivo; debe consultar todos los KPI de sus criterios."""
    criterios: list[Criterio]
    linea_base: dict[str, float] | None = None
    """Valor de cada KPI de los criterios en el periodo base. Se rellena en H4 a partir de los
    datos de 2024; mientras tanto es ``None`` (no se inventa)."""

    @model_validator(mode="after")
    def _criterios_coherentes(self) -> Objetivo:
        repetidos = sorted(k for k, n in Counter(c.kpi for c in self.criterios).items() if n > 1)
        if repetidos:
            raise ValueError(f"objetivo {self.id}: KPI repetido en los criterios: {repetidos}")
        for c in self.criterios:
            if c.papel == "principal" and c.comparacion.tipo != "umbral":
                meta, sentido = c.comparacion.meta, c.comparacion.sentido
                contraria = meta <= 0 if sentido == "al_menos" else meta >= 0
                if contraria:
                    raise ValueError(
                        f"objetivo {self.id}: el criterio principal {c.kpi} tiene meta {meta:g} "
                        f"con sentido {sentido}; una variación principal debe ser una mejora "
                        "(al_menos con meta > 0 o como_maximo con meta < 0)"
                    )
        pesos = [c.peso for c in self.criterios if c.papel == "principal"]
        if not pesos:
            raise ValueError(f"objetivo {self.id}: necesita al menos un criterio principal")
        if not math.isclose(sum(pesos), 1.0, abs_tol=1e-9):
            raise ValueError(
                f"objetivo {self.id}: los pesos de los criterios principales suman "
                f"{sum(pesos):g}, no 1"
            )
        if self.linea_base is not None:
            esperados = {c.kpi for c in self.criterios}
            if set(self.linea_base) != esperados:
                raise ValueError(
                    f"objetivo {self.id}: linea_base tiene {sorted(self.linea_base)}; debe dar "
                    f"un valor a cada KPI de los criterios {sorted(esperados)}"
                )
        return self

    @property
    def principales(self) -> list[Criterio]:
        return [c for c in self.criterios if c.papel == "principal"]

    @property
    def guardarrailes(self) -> list[Criterio]:
        return [c for c in self.criterios if c.papel == "guardarrail"]


class SeleccionHuespedes(_Modelo):
    """Qué huéspedes marca una regla de guest_flag: los de valor en el percentil
    ``percentil_valor`` o superior (valor = importe en EUR de las reservas no canceladas de las
    que es titular en los últimos ``meses_valor`` meses, sobre el golden record), menos una
    ``fraccion_control`` elegida con un hash determinista del golden record (grupo de control)."""

    percentil_valor: float = Field(gt=0, lt=1)
    fraccion_control: float = Field(gt=0, le=0.5)
    meses_valor: int = Field(gt=0, le=36)


class ReglaPms(_Modelo):
    """Fila que una acción de reverse ETL escribe en el PMS."""

    tabla: Literal["guest_flag", "rate_restriction"]
    valor: str
    """``guest_flag.flag`` o ``rate_restriction.rule``; debe estar en el vocabulario del
    contrato (``restricciones``)."""
    parametro: int | None = None
    """``rate_restriction.parametro``: antelación mínima en días (``deposito_obligatorio``)
    o noches mínimas (``estancia_minima``). Obligatorio en ``rate_restriction``; no procede en
    ``guest_flag``."""
    seleccion: SeleccionHuespedes | None = None
    """Solo en guest_flag: a quién se marca (ver SeleccionHuespedes)."""

    @model_validator(mode="after")
    def _seleccion_solo_en_guest_flag(self) -> ReglaPms:
        if self.seleccion is not None and self.tabla != "guest_flag":
            raise ValueError(f"regla {self.valor}: seleccion solo procede en guest_flag")
        return self

    @model_validator(mode="after")
    def _parametro_segun_tabla(self) -> ReglaPms:
        if self.tabla == "rate_restriction" and self.parametro is None:
            raise ValueError(f"regla {self.valor}: rate_restriction exige parametro")
        if self.tabla == "guest_flag" and self.parametro is not None:
            raise ValueError(f"regla {self.valor}: guest_flag no lleva parametro")
        return self


MADUREZ_RESERVA_DIAS = 30
"""Días que deben pasar desde el fin de una ventana por fecha de reserva hasta la fecha de
corte en que se lee el estado de las reservas (cancelada o no)."""


class Evaluacion(_Modelo):
    """Ventana de evaluación de una acción: qué fecha decide si un hecho entra en ella."""

    base: Literal["llegada", "reserva", "estancia", "publicacion"]
    """Fecha que sitúa cada hecho: ``arrival_date`` (cohorte de llegada), ``booked_at``,
    ``stay_date`` o ``posted_at`` (reseñas)."""
    desde: date
    hasta: date
    """Primer y último día (incluidos); ``hasta - desde + 1 == ventana_dias``."""
    corte: date
    """Fecha en que se leen los datos (el estado de las reservas): ``corte >= hasta`` y, con
    base ``reserva``, al menos ``MADUREZ_RESERVA_DIAS`` después de ``hasta``."""
    reservas_desde: date | None = None
    """Si se indica, solo cuentan las reservas creadas desde esa fecha (no antes del inicio)."""


class Accion(_Modelo):
    id: str
    nombre: str
    objetivos: list[str]
    disparador: str
    descripcion: str
    responsable: str
    kpi_exito: str
    criterio_exito: Comparacion
    guardarrailes: list[Criterio]
    ventana_dias: int = Field(gt=0)
    """Ventana de evaluación: ``ventana_dias`` días desde ``inicio``."""
    inicio: date
    """Primer día de la intervención."""
    fin: date | None = None
    """Último día de la intervención; ``None`` si sigue activa (no termina con la ventana)."""
    evaluacion: Evaluacion
    metodo_evaluacion: Literal["antes_despues", "grupo_control", "diferencias_en_diferencias"]
    ambito: str
    mecanismo: Literal["manual", "reverse_etl"]
    regla_pms: ReglaPms | None = None
    """Obligatoria si ``mecanismo`` es ``reverse_etl`` y prohibida si es ``manual``."""
    hoteles_piloto: list[str] | None = None
    hoteles_control: list[str] | None = None
    nota_docente: str | None = None
    """Nota para el libro (por ejemplo, el capítulo que usa la acción como lección); el
    documento de la organización no la muestra."""

    @model_validator(mode="after")
    def _guardarrailes_y_grupos(self) -> Accion:
        for g in self.guardarrailes:
            if g.papel != "guardarrail":
                raise ValueError(
                    f"acción {self.id}: {g.kpi} figura como guardarraíl con papel {g.papel}"
                )
        if (self.mecanismo == "reverse_etl") != (self.regla_pms is not None):
            raise ValueError(
                f"acción {self.id}: regla_pms es obligatoria con mecanismo reverse_etl y no "
                "procede con mecanismo manual"
            )
        ev = self.evaluacion
        if (ev.hasta - ev.desde).days + 1 != self.ventana_dias:
            raise ValueError(
                f"acción {self.id}: la evaluación ({ev.desde} a {ev.hasta}) no dura "
                f"ventana_dias ({self.ventana_dias})"
            )
        if ev.desde < self.inicio:
            raise ValueError(f"acción {self.id}: la evaluación empieza antes del inicio")
        if ev.reservas_desde is not None and ev.reservas_desde < self.inicio:
            raise ValueError(f"acción {self.id}: reservas_desde anterior al inicio")
        if ev.corte < ev.hasta:
            raise ValueError(f"acción {self.id}: corte anterior al fin de la evaluación")
        if ev.base == "reserva" and (ev.corte - ev.hasta).days < MADUREZ_RESERVA_DIAS:
            raise ValueError(
                f"acción {self.id}: con base reserva el corte debe ser al menos "
                f"{MADUREZ_RESERVA_DIAS} días posterior al fin de la evaluación"
            )
        if self.fin is not None and self.fin < self.inicio:
            raise ValueError(
                f"acción {self.id}: fin ({self.fin}) anterior a inicio ({self.inicio})"
            )
        comunes = set(self.hoteles_piloto or []) & set(self.hoteles_control or [])
        if comunes:
            raise ValueError(
                f"acción {self.id}: hoteles a la vez piloto y control: {sorted(comunes)}"
            )
        return self


class Semaforo(_Modelo):
    verde: float
    ambar: float

    @model_validator(mode="after")
    def _orden(self) -> Semaforo:
        if not 0 < self.ambar < self.verde <= 1:
            raise ValueError("semáforo: se exige 0 < ambar < verde <= 1")
        return self


class Seguimiento(_Modelo):
    """Regla del seguimiento intermedio del índice de logro."""

    frecuencia: Literal["mensual", "trimestral"]
    comparacion: Literal["ytd_vs_ytd_base"]
    """Acumulado del año en curso hasta el cierre del periodo frente al mismo tramo del año
    base (``logro.ventanas_ytd``)."""
    descripcion: str | None = None


class Horizonte(_Modelo):
    """Histórico que simula el PMS (H3): debe cubrir el año base, el evaluado y las ventanas
    de todas las acciones."""

    inicio: date
    fin: date
    historia_huespedes_desde: date
    """Desde cuándo hay estancias de huéspedes (aunque el resto del PMS empiece en ``inicio``):
    la tasa de repetición del año base mira 24 meses atrás, así que debe ser como tarde el 1 de
    enero de ``periodo_base - 2``."""


class Supuesto(_Modelo):
    """Decisión de diseño o supuesto que cambia una cifra (sección «Supuestos» del documento)."""

    id: str
    nombre: str
    texto: str


class Riesgo(_Modelo):
    id: str
    nombre: str
    efecto: str
    mitigacion: str
    responsable: str
    """Actor que vigila el riesgo y activa la mitigación."""


class CambioDocumento(_Modelo):
    version: str
    fecha: date
    cambio: str
    aprobado_por: str
    """Actor que aprueba el cambio."""


class Documento(_Modelo):
    """Control del documento: propietario, custodio, estado, aprobación e historial."""

    propietario: str
    custodio: str
    estado: Literal["borrador", "en_revision", "aprobado"]
    fecha_aprobacion: date | None = None
    revision_ordinaria: str
    revision_extraordinaria: str
    historial: list[CambioDocumento] = Field(min_length=1)

    @model_validator(mode="after")
    def _aprobacion(self) -> Documento:
        if self.estado == "aprobado" and self.fecha_aprobacion is None:
            raise ValueError("documento: un documento aprobado necesita fecha_aprobacion")
        fechas = [c.fecha for c in self.historial]
        if fechas != sorted(fechas):
            raise ValueError("documento: el historial debe estar en orden cronológico")
        return self


class Hotel(_Modelo):
    codigo: str = Field(pattern=r"^[A-Z]{3}$")
    nombre: str
    isla: Literal["Tenerife", "Gran Canaria", "Lanzarote", "Fuerteventura"]
    municipio: str
    tipo: Literal["urban", "resort", "all_inclusive", "rural"]
    estrellas: int = Field(ge=1, le=5)
    habitaciones: int = Field(gt=0)


class MuestraMinima(_Modelo):
    """Mínimo de unidades muestrales (una métrica base del KPI: reservas, reseñas…) en el periodo
    y en el de referencia para que una alerta pueda saltar: por debajo, el KPI de un mes varía
    varios puntos solo por azar."""

    metrica: str
    minimo: int = Field(gt=0)


class Alerta(_Modelo):
    """Regla de alerta sobre un KPI (capítulos 2 y 18), en el último periodo cerrado (tipo
    ``periodo``) de cada ámbito. «umbral»: el KPI se compara con ``umbral`` en el ``sentido`` dado.
    «deterioro»: el KPI empeora más de ``margen`` frente al mismo periodo del año anterior del
    propio ámbito (por_encima: valor > referencia + margen; por_debajo: valor < referencia −
    margen). Con ``muestra_minima``, no salta si el periodo o su referencia tienen menos
    unidades. Si salta y hay ``accion`` (con mecanismo reverse_etl), su regla_pms se escribe en el
    PMS. «anomalia»: un día marcado como anómalo en ml.anomalia_kpi para el KPI; solo avisa."""

    id: str = Field(pattern=r"^AL\d+$")
    nombre: str
    tipo: Literal["umbral", "deterioro", "anomalia"]
    kpi: str
    ambito: Literal["hotel", "cadena"]
    periodo: Literal["mes"] | None = None
    sentido: Literal["por_encima", "por_debajo"] | None = None
    umbral: float | None = None
    margen: float | None = Field(default=None, gt=0)
    muestra_minima: MuestraMinima | None = None
    destinatario: str
    accion: str | None = None

    @model_validator(mode="after")
    def _campos_segun_tipo(self) -> Alerta:
        if self.tipo in ("umbral", "deterioro"):
            if self.periodo is None or self.sentido is None:
                raise ValueError(
                    f"alerta {self.id}: una alerta de {self.tipo} exige periodo y sentido"
                )
            if self.tipo == "umbral" and (self.umbral is None or self.margen is not None):
                raise ValueError(
                    f"alerta {self.id}: una alerta de umbral exige umbral (sin margen)"
                )
            if self.tipo == "deterioro" and (self.margen is None or self.umbral is not None):
                raise ValueError(
                    f"alerta {self.id}: una alerta de deterioro exige margen (sin umbral fijo)"
                )
        if self.tipo == "anomalia":
            de_umbral = (self.periodo, self.sentido, self.umbral, self.margen, self.muestra_minima)
            if any(x is not None for x in de_umbral):
                raise ValueError(
                    f"alerta {self.id}: una anomalía no lleva periodo, sentido, umbral, margen "
                    "ni muestra mínima"
                )
            if self.accion is not None:
                raise ValueError(f"alerta {self.id}: una anomalía solo avisa (sin acción)")
            from .alertas import KPI_DIARIOS

            if self.kpi not in KPI_DIARIOS:
                raise ValueError(
                    f"alerta {self.id}: las anomalías solo existen para {sorted(KPI_DIARIOS)}"
                )
        return self


class Definicion(_Modelo):
    version: str
    organizacion: str
    periodo_base: int
    periodo_evaluado: int
    hoteles: list[Hotel]
    actores: list[Actor]
    medidas_raw: list[MedidaRaw]
    metricas_base: list[MetricaBase]
    kpis: list[Kpi]
    objetivos: list[Objetivo]
    acciones: list[Accion]
    semaforo: Semaforo
    seguimiento: Seguimiento
    horizonte_simulado: Horizonte
    desagregacion_regimen: dict[str, float]
    """Parte del precio de un paquete que es alojamiento, por régimen (``rate_plan.board``);
    el resto es restauración. Las claves se contrastan con el contrato del PMS."""
    supuestos: list[Supuesto] = []
    riesgos: list[Riesgo] = []
    alertas: list[Alerta] = []
    documento: Documento | None = None

    @model_validator(mode="after")
    def _integridad_referencial(self) -> Definicion:
        ids = (
            [h.codigo for h in self.hoteles]
            + [a.id for a in self.actores]
            + [m.id for m in self.medidas_raw]
            + [m.id for m in self.metricas_base]
            + [k.id for k in self.kpis]
            + [o.id for o in self.objetivos]
            + [a.id for a in self.acciones]
            + [r.id for r in self.riesgos]
            + [s.id for s in self.supuestos]
            + [a.id for a in self.alertas]
        )
        duplicados = sorted(i for i, n in Counter(ids).items() if n > 1)
        if duplicados:
            raise ValueError(f"identificadores duplicados: {duplicados}")
        if self.periodo_evaluado <= self.periodo_base:
            raise ValueError("periodo_evaluado debe ser posterior a periodo_base")
        horiz = self.horizonte_simulado
        if horiz.inicio > date(self.periodo_base, 1, 1) or horiz.fin < date(
            self.periodo_evaluado, 12, 31
        ):
            raise ValueError(
                f"horizonte_simulado ({horiz.inicio} a {horiz.fin}) no cubre el periodo base "
                f"{self.periodo_base} y el evaluado {self.periodo_evaluado}"
            )
        if (
            horiz.historia_huespedes_desde > date(self.periodo_base - 2, 1, 1)
            or horiz.historia_huespedes_desde > horiz.inicio
        ):
            raise ValueError(
                f"horizonte_simulado: historia_huespedes_desde ({horiz.historia_huespedes_desde}) "
                f"debe ser como tarde el {date(self.periodo_base - 2, 1, 1)} (24 meses antes "
                "del periodo base) y no posterior al inicio"
            )
        for regimen, parte in self.desagregacion_regimen.items():
            if not 0 < parte <= 1:
                raise ValueError(f"desagregacion_regimen: {regimen} debe estar en (0, 1]")
        if self.desagregacion_regimen.get("RO", 1.0) != 1.0:
            raise ValueError("desagregacion_regimen: RO (solo alojamiento) debe ser 1")

        hoteles = {h.codigo for h in self.hoteles}
        actores = {a.id: a for a in self.actores}
        medidas = {m.id for m in self.medidas_raw}
        metricas = {m.id for m in self.metricas_base}
        kpis = {k.id: k for k in self.kpis}
        objetivos = {o.id for o in self.objetivos}

        def exige(valor: str, conjunto, que: str, donde: str) -> None:
            if valor not in conjunto:
                raise ValueError(f"{donde}: {que} inexistente {valor!r}")

        for a in self.actores:
            for k in a.kpis:
                exige(k, kpis, "KPI", f"actor {a.id}")
        for m in self.metricas_base:
            for med in m.medidas:
                exige(med, medidas, "medida raw", f"métrica {m.id}")
        for k in self.kpis:
            for m in k.metricas:
                exige(m, metricas, "métrica base", f"KPI {k.id}")
            for a in k.actores:
                exige(a, actores, "actor", f"KPI {k.id}")
                if k.id not in actores[a].kpis:
                    raise ValueError(f"KPI {k.id} cita al actor {a}, pero el actor no lo incluye")
        for a in self.actores:
            for k in a.kpis:
                if a.id not in kpis[k].actores:
                    raise ValueError(f"actor {a.id} incluye {k}, pero el KPI no cita al actor")
        for k in self.kpis:
            exige(k.propietario, actores, "propietario (actor)", f"KPI {k.id}")
            if k.propietario not in k.actores:
                raise ValueError(
                    f"KPI {k.id}: el propietario {k.propietario} no figura entre sus actores"
                )
        concordancia = {"al_menos": "subir", "como_maximo": "bajar"}
        for o in self.objetivos:
            exige(o.responsable, actores, "responsable (actor)", f"objetivo {o.id}")
            for c in o.criterios:
                exige(c.kpi, kpis, "KPI", f"objetivo {o.id}")
                if c.kpi not in actores[o.responsable].kpis:
                    raise ValueError(
                        f"objetivo {o.id}: el responsable {o.responsable} no consulta el KPI "
                        f"{c.kpi} de sus criterios"
                    )
                if c.papel != "principal":
                    continue
                sentido_kpi = kpis[c.kpi].sentido
                if sentido_kpi == "neutro":
                    raise ValueError(
                        f"objetivo {o.id}: el KPI {c.kpi} es neutro (de diagnóstico) "
                        "y no puede ser criterio principal"
                    )
                if concordancia[c.comparacion.sentido] != sentido_kpi:
                    raise ValueError(
                        f"objetivo {o.id}: el criterio principal {c.kpi} es "
                        f"{c.comparacion.sentido}, pero el KPI tiene sentido {sentido_kpi}"
                    )
        for ac in self.acciones:
            donde = f"acción {ac.id}"
            for o in ac.objetivos:
                exige(o, objetivos, "objetivo", donde)
            exige(ac.responsable, actores, "responsable (actor)", donde)
            exige(ac.kpi_exito, kpis, "KPI de éxito", donde)
            for g in ac.guardarrailes:
                exige(g.kpi, kpis, "KPI de guardarraíl", donde)
            for h in (ac.hoteles_piloto or []) + (ac.hoteles_control or []):
                exige(h, hoteles, "hotel", donde)
            if ac.inicio.year != self.periodo_evaluado:
                raise ValueError(
                    f"{donde}: inicio {ac.inicio} fuera del periodo evaluado "
                    f"{self.periodo_evaluado}"
                )
            fin_ventana = max(ac.inicio + timedelta(days=ac.ventana_dias), ac.evaluacion.corte)
            if fin_ventana > horiz.fin or (ac.fin is not None and ac.fin > horiz.fin):
                raise ValueError(
                    f"{donde}: la ventana o la intervención terminan después del horizonte "
                    f"simulado ({horiz.fin})"
                )
        for r in self.riesgos:
            exige(r.responsable, actores, "responsable (actor)", f"riesgo {r.id}")
        doc = self.documento
        if doc is not None:
            exige(doc.propietario, actores, "propietario (actor)", "documento")
            exige(doc.custodio, actores, "custodio (actor)", "documento")
            for c in doc.historial:
                exige(c.aprobado_por, actores, "aprobador (actor)", f"versión {c.version}")
            if doc.historial[-1].version != self.version:
                raise ValueError(
                    f"documento: la última versión del historial ({doc.historial[-1].version}) "
                    f"no es la versión vigente ({self.version})"
                )
            fecha = doc.fecha_aprobacion
            if fecha is not None and fecha.year > self.periodo_evaluado:
                raise ValueError("documento: aprobado después del periodo evaluado")
        acciones = {a.id: a for a in self.acciones}
        for al in self.alertas:
            exige(al.kpi, kpis, "KPI", f"alerta {al.id}")
            if al.muestra_minima and al.muestra_minima.metrica not in kpis[al.kpi].metricas:
                raise ValueError(
                    f"alerta {al.id}: la muestra mínima ({al.muestra_minima.metrica}) no es una "
                    f"métrica base del KPI {al.kpi}"
                )
            exige(al.destinatario, actores, "destinatario (actor)", f"alerta {al.id}")
            if al.kpi not in actores[al.destinatario].kpis:
                raise ValueError(
                    f"alerta {al.id}: el destinatario {al.destinatario} no consulta {al.kpi}"
                )
            if al.accion is not None:
                exige(al.accion, acciones, "acción", f"alerta {al.id}")
                if acciones[al.accion].mecanismo != "reverse_etl":
                    raise ValueError(f"alerta {al.id}: la acción {al.accion} no es de reverse ETL")
        return self
