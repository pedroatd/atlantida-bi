{{ config(contract={'enforced': true}) }}
-- Cada criterio de cada objetivo con su valor base (periodo base) y actual (periodo evaluado),
-- anual y en el seguimiento mensual del acumulado del año (YTD: del 1 de enero al cierre de cada
-- mes, frente al mismo tramo del año base), para la cadena y cada hotel de la dimensión. El
-- ámbito '-1' (hechos sin hotel) no es un hotel: no tiene objetivos.
-- La base es el KPI del periodo base calculado con los datos (la línea base de atlantida.yml está
-- vacía hasta fijarla con ellos). Sin valor, o con una variación relativa sobre 0 (base_cero), el
-- criterio queda sin dato. completo: los dos periodos han madurado (int_periodos.completo).
with par as (
    select
        max(valor) filter (where clave = 'periodo_base') as periodo_base,
        max(valor) filter (where clave = 'periodo_evaluado') as periodo_evaluado,
        max(valor) filter (where clave = 'tolerancia')::double precision as tolerancia
    from {{ ref('def_parametro') }}
),

evaluaciones as (
    select
        'anual' as evaluacion,
        null::integer as mes,
        periodo_evaluado as periodo_actual,
        periodo_base as periodo_previo
    from par
    union all
    select
        'ytd' as evaluacion,
        m as mes,
        periodo_evaluado || '-YTD-' || lpad(m::text, 2, '0') as periodo_actual,
        periodo_base || '-YTD-' || lpad(m::text, 2, '0') as periodo_previo
    from par
    cross join generate_series(1, 12) as m
),

ambitos as (
    select codigo as ambito from {{ ref('dim_hotel_actual') }}
    union all
    select 'CADENA' as ambito
),

cruce as (
    select
        c.objetivo_id,
        c.orden,
        c.kpi,
        c.papel,
        c.peso,
        c.tipo,
        c.sentido,
        c.meta,
        e.evaluacion,
        e.mes,
        a.ambito,
        vb.valor as base,
        va.valor as actual,
        coalesce(vb.completo and va.completo, false) as completo,
        par.tolerancia
    from {{ ref('def_criterio') }} as c
    cross join evaluaciones as e
    cross join ambitos as a
    cross join par
    left join {{ ref('kpi_periodo') }} as vb
        on e.periodo_previo = vb.periodo_id and a.ambito = vb.ambito and c.kpi = vb.kpi
    left join {{ ref('kpi_periodo') }} as va
        on e.periodo_actual = va.periodo_id and a.ambito = va.ambito and c.kpi = va.kpi
),

magnitudes as (
    select
        *,
        {{ magnitud_criterio('tipo', 'base', 'actual') }} as magnitud
    from cruce
),

cumplimiento as (
    select
        *,
        {{ cumple_criterio('sentido', 'magnitud', 'meta', 'tolerancia') }} as cumple
    from magnitudes
)

select
    objetivo_id::text as objetivo_id,
    orden::integer as orden,
    kpi::text as kpi,
    papel::text as papel,
    peso::double precision as peso,
    tipo::text as tipo,
    sentido::text as sentido,
    meta::double precision as meta,
    evaluacion::text as evaluacion,
    mes::integer as mes,
    ambito::text as ambito,
    base::double precision as base,
    actual::double precision as actual,
    magnitud::double precision as magnitud,
    cumple,
    (
        {{ progreso_criterio('papel', 'tipo', 'sentido', 'meta', 'base', 'actual', 'magnitud', 'cumple') }}
    )::double precision as progreso,
    coalesce(tipo = 'variacion_relativa' and base = 0, false) as base_cero,
    completo
from cumplimiento
