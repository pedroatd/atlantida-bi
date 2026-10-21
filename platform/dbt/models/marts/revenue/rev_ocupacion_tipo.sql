-- Revenue manager. Cupos por tipo de habitación: habitaciones de cada tipo y noches vendidas por
-- día. No descuenta las habitaciones fuera de servicio (la ocupación oficial, con el inventario
-- disponible, está en marts_kpi.kpi_base_diaria). Fórmula del documento de definición (formulas_kpi).
{%- set f = formulas_kpi() %}
with inventario as (
    select
        hotel_id,
        tipo_codigo as tipo_habitacion,
        count(*) as habitaciones
    from {{ ref('dim_habitacion') }}
    where habitacion_sk <> -1
    group by hotel_id, tipo_codigo
),

dias as (
    select distinct fecha_estancia as fecha from {{ ref('fct_noche_estancia') }}
),

vendidas as (
    select
        n.fecha_estancia as fecha,
        coalesce(hab.hotel_id, n.hotel_id) as hotel_id,
        coalesce(hab.tipo_codigo, '?') as tipo_habitacion,
        count(*) as noches_vendidas
    from {{ ref('fct_noche_estancia') }} as n
    left join {{ ref('dim_habitacion') }} as hab on n.habitacion_sk = hab.habitacion_sk
    group by n.fecha_estancia, coalesce(hab.hotel_id, n.hotel_id), coalesce(hab.tipo_codigo, '?')
),

rejilla as (
    select
        d.fecha,
        i.hotel_id,
        i.tipo_habitacion,
        i.habitaciones
    from dias as d
    cross join inventario as i
    union all
    -- noches de habitaciones que no están en la dimensión: no se pierden
    select
        v.fecha,
        v.hotel_id,
        v.tipo_habitacion,
        0 as habitaciones
    from vendidas as v
    where not exists (
        select 1
        from inventario as i
        where i.hotel_id = v.hotel_id and i.tipo_habitacion = v.tipo_habitacion
    )
),

bases as (
    select
        r.fecha,
        coalesce(h.codigo, '-1') as hotel,
        r.tipo_habitacion,
        r.habitaciones as habitaciones_disponibles,
        coalesce(v.noches_vendidas, 0) as noches_vendidas
    from rejilla as r
    left join vendidas as v
        on r.fecha = v.fecha and r.hotel_id = v.hotel_id and r.tipo_habitacion = v.tipo_habitacion
    left join {{ ref('dim_hotel_actual') }} as h on r.hotel_id = h.hotel_id
)

select
    fecha,
    hotel::text as hotel,
    tipo_habitacion::text as tipo_habitacion,
    habitaciones_disponibles::integer as habitaciones,
    noches_vendidas::integer as noches_vendidas,
    ({{ f['ocupacion'] }})::double precision as ocupacion
from bases
