-- Habitaciones de cada hotel y día, las bloqueadas (fuera de servicio) y las disponibles.
with noches as (
    select fecha_estancia from {{ ref('stg_pms__noches') }}
),

dias as (
    select d::date as fecha
    from generate_series(
        (select min(fecha_estancia) from noches),
        (select max(fecha_estancia) from noches),
        interval '1 day'
    ) as d
),

habitaciones as (
    select
        hotel_id,
        count(*) as habitaciones
    from {{ ref('stg_pms__habitaciones') }}
    group by hotel_id
),

bloqueadas as (
    select
        h.hotel_id,
        d.fecha,
        count(distinct b.habitacion_id) as bloqueadas
    from {{ ref('stg_pms__bloqueos') }} as b
    inner join {{ ref('stg_pms__habitaciones') }} as h on b.habitacion_id = h.habitacion_id
    inner join dias as d on d.fecha between b.fecha_inicio and b.fecha_fin
    group by h.hotel_id, d.fecha
)

select
    h.hotel_id,
    d.fecha,
    h.habitaciones,
    coalesce(b.bloqueadas, 0) as bloqueadas,
    h.habitaciones - coalesce(b.bloqueadas, 0) as disponibles
from habitaciones as h
cross join dias as d
left join bloqueadas as b on h.hotel_id = b.hotel_id and d.fecha = b.fecha
