{{ config(contract={'enforced': true}) }}
-- KPI diarios (latencia D-1) por hotel y cadena: los que se calculan con métricas de cada día.
-- Días del hecho de ocupación; los hoteles se unen con left join: un hecho sin hotel en la
-- dimensión cae en el ámbito '-1' (y en la cadena). Las métricas aditivas valen 0 sin hechos.
{%- set formulas = formulas_kpi() %}
{%- set kpis = ['ocupacion', 'adr', 'revpar', 'trevpar', 'cuota_directa'] %}
{%- set metricas = ['habitaciones_disponibles', 'noches_vendidas', 'noches_vendidas_directo',
                    'ingreso_habitaciones', 'ingreso_otros'] %}
with dias as (
    select
        min(fecha) as primero,
        max(fecha) as ultimo
    from {{ ref('fct_ocupacion_diaria') }}
),

bases as (
    select
        a.fecha,
        {%- for m in metricas %}
            coalesce(sum(a.valor) filter (where a.metrica = '{{ m }}'), 0) as {{ m }},
        {%- endfor %}
        case when grouping(h.codigo) = 1 then 'CADENA' else coalesce(h.codigo, '-1') end as ambito
    from {{ ref('int_kpi_aportaciones_diarias') }} as a
    inner join dias as d on a.fecha >= d.primero and a.fecha <= d.ultimo
    left join {{ ref('dim_hotel_actual') }} as h on a.hotel_id = h.hotel_id
    where
        a.valida_hasta is null
        and a.metrica in ({%- for m in metricas %}'{{ m }}'{{ ", " if not loop.last }}{%- endfor %})
    group by grouping sets ((a.fecha, h.codigo), (a.fecha))
)

select
    b.fecha,
    b.ambito::text as ambito,
    k.kpi::text as kpi,
    k.valor::double precision as valor
from bases as b
cross join lateral (
    values
    {%- for kpi in kpis %}
        ('{{ kpi }}', ({{ formulas[kpi] }})::double precision){{ "," if not loop.last }}
    {%- endfor %}
) as k (kpi, valor)
