{{ config(indexes=[{'columns': ['fecha_estancia']}, {'columns': ['hotel_id', 'fecha_estancia']}]) }}
-- Hecho de transacción al grano noche × habitación: la base de ocupación, ADR y RevPAR. La
-- comisión del canal se devenga por noche con el tipo vigente en la fecha de la reserva. Las
-- versiones del hotel y del huésped son las vigentes al empezar el día de estancia (hora canaria).
with n as (select * from {{ ref('stg_pms__noches') }}),

r as (
    select
        reserva_id,
        hotel_id,
        canal_id,
        tipo_canal,
        es_directo,
        plan_tarifa_id,
        huesped_id,
        tasa_comision
    from {{ ref('int_reservas') }}
),

grupos as (
    select
        huesped_id,
        huesped_golden_id
    from {{ ref('int_huespedes_grupos') }}
),

fichas as (
    select
        huesped_id,
        pais_codigo
    from {{ ref('stg_pms__huespedes') }}
),

noches as (
    select
        n.noche_id,
        n.reserva_id,
        n.habitacion_id,
        n.fecha_estancia,
        {{ inicio_dia_local('n.fecha_estancia') }} as inicio_dia,
        n.ingreso_habitacion,
        r.hotel_id,
        r.canal_id,
        r.tipo_canal,
        r.es_directo,
        r.plan_tarifa_id,
        r.tasa_comision,
        f.pais_codigo,
        coalesce(g.huesped_golden_id, -1) as huesped_golden_id
    from n
    left join r on n.reserva_id = r.reserva_id
    left join grupos as g on r.huesped_id = g.huesped_id
    left join fichas as f on r.huesped_id = f.huesped_id
)

select
    x.noche_id,
    x.reserva_id,
    x.fecha_estancia,
    coalesce(h.hotel_sk, -1) as hotel_sk,
    x.hotel_id,
    coalesce(hab.habitacion_sk, -1) as habitacion_sk,
    coalesce(c.canal_sk, -1) as canal_sk,
    x.canal_id,
    x.tipo_canal,
    x.es_directo,
    coalesce(t.tarifa_sk, -1) as tarifa_sk,
    coalesce(hu.huesped_sk, -1) as huesped_sk,
    x.huesped_golden_id,
    coalesce(m.meteo_sk, -1) as meteo_sk,
    coalesce(me.mercado_sk, -1) as mercado_sk,
    x.ingreso_habitacion,
    x.ingreso_habitacion * x.tasa_comision as comision
from noches as x
left join {{ ref('dim_hotel') }} as h
    on x.hotel_id = h.hotel_id and x.inicio_dia >= h.valido_desde and x.inicio_dia < h.valido_hasta
left join {{ ref('dim_hotel_actual') }} as ha on x.hotel_id = ha.hotel_id
left join {{ ref('dim_habitacion') }} as hab on x.habitacion_id = hab.habitacion_id
left join {{ ref('dim_canal') }} as c on x.canal_id = c.canal_id
left join {{ ref('dim_tarifa') }} as t on x.plan_tarifa_id = t.plan_tarifa_id
left join {{ ref('dim_huesped') }} as hu
    on
        x.huesped_golden_id = hu.huesped_golden_id
        and x.inicio_dia >= hu.valido_desde
        and x.inicio_dia < hu.valido_hasta
left join {{ ref('dim_meteo') }} as m on ha.isla = m.isla and x.fecha_estancia = m.fecha
left join {{ ref('dim_mercado') }} as me on x.pais_codigo = me.pais_codigo
