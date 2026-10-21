-- Métricas base aditivas por día y hotel, una columna por métrica (generadas desde
-- atlantida.yml): Superset calcula cada KPI con su fórmula sobre estas sumas, así un KPI
-- agregado a cualquier periodo o grupo de hoteles es correcto (cociente de sumas, nunca media de
-- cocientes). Reservas netas (y las noches reservadas) con su estado en el corte de madurez de su
-- año (31 de diciembre + madurez_dias), como marts_kpi.kpi_periodo y el scorecard: un año agregado
-- (cualquier grupo de hoteles) da la cifra oficial. Un mes agregado aquí también lee el corte del
-- año, más maduro que el de ese mes en kpi_periodo (la serie mensual oficial está allí). En el
-- año en curso el corte aún no ha llegado y cuenta el estado actual. con_costes: el mes tiene
-- cierre contable en ese hotel.
{%- set columnas = metricas_base_diarias() %}
with par as (
    select max(valor) filter (where clave = 'madurez_dias')::int as madurez_dias
    from {{ ref('def_parametro') }}
),

dias as (
    select
        min(o.fecha) as primero,
        max(o.fecha) as ultimo
    from {{ ref('fct_ocupacion_diaria') }} as o
),

actuales as (
    select
        a.hotel_id,
        a.fecha,
        a.metrica,
        sum(a.valor) as valor
    from {{ ref('int_kpi_aportaciones_diarias') }} as a
    cross join par
    where
        a.valida_hasta is null
        or a.valida_hasta > make_date(extract(year from a.fecha)::int, 12, 31) + par.madurez_dias
    group by a.hotel_id, a.fecha, a.metrica
),

pivote as (
    select
        hotel_id,
        fecha,
        {%- for m in columnas %}
            coalesce(sum(valor) filter (where metrica = '{{ m }}'), 0) as {{ m }},
        {%- endfor %}
        coalesce(sum(valor) filter (where metrica = 'coste_total'), 0) as coste_total,
        bool_or(metrica = 'coste_total') as hay_coste
    from actuales
    group by hotel_id, fecha
)

select
    p.fecha,
    coalesce(h.codigo, '-1')::text as hotel,
    h.isla::text as isla,
    h.tipo_hotel::text as tipo_hotel,
    coalesce(
        bool_or(p.hay_coste) over (partition by p.hotel_id, date_trunc('month', p.fecha)), false
    ) as con_costes,
    {%- for m in columnas %}
        p.{{ m }}::double precision as {{ m }},
    {%- endfor %}
    (p.coste_total + p.comisiones)::double precision as costes_operativos
from pivote as p
cross join dias as d
left join {{ ref('dim_hotel_actual') }} as h on p.hotel_id = h.hotel_id
-- Solo los días con ocupación registrada: sin días futuros (cohortes de llegada y reservas ya
-- creadas para fechas por venir), así un panel sin filtro no mezcla periodos inmaduros; ni días
-- anteriores, que solo tendrían las reservas creadas antes del primer día (periodos parciales que
-- kpi_periodo tampoco abre).
where p.fecha between d.primero and d.ultimo
