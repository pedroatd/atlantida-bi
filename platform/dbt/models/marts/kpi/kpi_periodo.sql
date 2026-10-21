{{ config(contract={'enforced': true}) }}
-- KPI de atlantida.yml por periodo y ámbito, con las fórmulas generadas (formulas_kpi()). Las
-- métricas aditivas llegan densas (0 sin hechos); lo publicado por el compset y los días en rojo,
-- solo si hay dato, así que sus KPI quedan nulos sin medida. Incluye el ámbito '-1' si existe.
{%- set formulas = formulas_kpi() %}
with bases as (
    select
        periodo_id,
        {%- for m in metricas_base_ids() %}
            max(valor) filter (where metrica = '{{ m }}') as {{ m }},
        {%- endfor %}
        ambito
    from {{ ref('kpi_metricas_base') }}
    group by periodo_id, ambito
)

select
    b.periodo_id::text as periodo_id,
    p.tipo_periodo::text as tipo_periodo,
    p.anio::integer as anio,
    p.mes::integer as mes,
    p.desde,
    p.hasta,
    p.completo,
    b.ambito::text as ambito,
    k.kpi::text as kpi,
    k.valor::double precision as valor
from bases as b
inner join {{ ref('int_periodos') }} as p on b.periodo_id = p.periodo_id
cross join lateral (
    values
    {%- for kpi, expresion in formulas.items() %}
        ('{{ kpi }}', ({{ expresion }})::double precision){{ "," if not loop.last }}
    {%- endfor %}
) as k (kpi, valor)
