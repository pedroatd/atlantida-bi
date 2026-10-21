-- Marketing: cuota directa de captación semanal (noches netas reservadas por fecha de creación,
-- con el estado actual) por hotel, marcando las semanas en que el hotel tiene una campaña. Usa el
-- estado actual de las reservas, no el estado en el corte (madurez a 30 días) que pide la
-- definición: por eso las columnas llevan el sufijo _actual, como en la capa semántica, y no
-- coinciden con el KPI cuota_directa_captacion de marts_kpi.
{%- set f = formulas_kpi() %}
with semanas_campana as (
    select distinct
        ch.hotel_id,
        generate_series(date_trunc('week', c.fecha_inicio), c.fecha_fin, interval '1 week')::date as semana
    from {{ ref('stg_pms__campanas') }} as c
    inner join {{ ref('stg_pms__campanas_hoteles') }} as ch on c.campana_id = ch.campana_id
),

bases as (
    select
        hotel_id,
        date_trunc('week', fecha_reserva)::date as semana,
        (sum(noches) filter (where not es_cancelada))::numeric as noches_por_reserva,
        (sum(noches) filter (where not es_cancelada and es_directo))::numeric as noches_reservadas_directo
    from {{ ref('fct_reserva') }}
    group by 1, 2
)

select
    b.semana,
    h.codigo as hotel,
    s.hotel_id is not null as en_campana,
    b.noches_por_reserva as noches_por_reserva_actual,
    b.noches_reservadas_directo as noches_reservadas_directo_actual,
    ({{ f['cuota_directa_captacion'] }})::double precision as cuota_directa_captacion_actual
from bases as b
inner join {{ ref('dim_hotel_actual') }} as h on b.hotel_id = h.hotel_id
left join semanas_campana as s on b.hotel_id = s.hotel_id and b.semana = s.semana
