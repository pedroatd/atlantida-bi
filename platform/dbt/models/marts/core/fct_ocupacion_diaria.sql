{{ config(indexes=[{'columns': ['hotel_id', 'fecha'], 'unique': True}]) }}
-- Snapshot periódico: una fila por hotel y día con el inventario y lo vendido. Las medidas son
-- aditivas entre hoteles y semiaditivas en el tiempo (habitaciones, bloqueadas y disponibles son
-- niveles de inventario: no se suman entre días como saldos, sino como habitaciones-noche).
-- Las noches de un hotel-día sin inventario no se pierden: tienen fila con inventario 0.
with ventas as (
    select
        hotel_id,
        fecha_estancia as fecha,
        count(*) as noches_vendidas,
        count(*) filter (where es_directo) as noches_vendidas_directo,
        sum(ingreso_habitacion) as ingreso_habitaciones
    from {{ ref('fct_noche_estancia') }}
    group by hotel_id, fecha_estancia
),

dias as (
    select
        coalesce(i.hotel_id, v.hotel_id) as hotel_id,
        coalesce(i.fecha, v.fecha) as fecha,
        coalesce(i.habitaciones, 0) as habitaciones,
        coalesce(i.bloqueadas, 0) as bloqueadas,
        coalesce(i.disponibles, 0) as disponibles,
        coalesce(v.noches_vendidas, 0) as noches_vendidas,
        coalesce(v.noches_vendidas_directo, 0) as noches_vendidas_directo,
        coalesce(v.ingreso_habitaciones, 0) as ingreso_habitaciones
    from {{ ref('int_inventario_diario') }} as i
    full join ventas as v on i.hotel_id = v.hotel_id and i.fecha = v.fecha
)

select
    d.hotel_id,
    coalesce(h.hotel_sk, -1) as hotel_sk,
    d.fecha,
    d.habitaciones,
    d.bloqueadas,
    d.disponibles,
    d.noches_vendidas,
    d.noches_vendidas_directo,
    d.ingreso_habitaciones
from dias as d
left join {{ ref('dim_hotel') }} as h
    on
        d.hotel_id = h.hotel_id
        and {{ inicio_dia_local('d.fecha') }} >= h.valido_desde
        and {{ inicio_dia_local('d.fecha') }} < h.valido_hasta
