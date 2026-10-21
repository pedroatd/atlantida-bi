-- Experiencia: NPS mensual por hotel y fuente de la reseña (las fuentes responden distinto).
{%- set f = formulas_kpi() %}
with bases as (
    select
        date_trunc('month', fecha_publicacion)::date as mes,
        hotel_id,
        fuente,
        (count(*) filter (where es_promotor))::numeric as promotores,
        (count(*) filter (where es_detractor))::numeric as detractores,
        (count(*) filter (where tiene_recomendacion))::numeric as respuestas_recomendacion
    from {{ ref('fct_resena') }}
    group by 1, 2, 3
)

select
    b.mes,
    h.codigo as hotel,
    b.fuente,
    b.promotores,
    b.detractores,
    b.respuestas_recomendacion,
    ({{ f['nps'] }})::double precision as nps
from bases as b
inner join {{ ref('dim_hotel_actual') }} as h on b.hotel_id = h.hotel_id
