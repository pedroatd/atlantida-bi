{{ config(
    contract={'enforced': true},
    indexes=[{'columns': ['fecha_reserva']}, {'columns': ['fecha_llegada']}, {'columns': ['hotel_id']}]
) }}
-- Hecho de transacción: una fila por reserva (grano). El localizador es una dimensión degenerada.
-- Las fechas de reserva, llegada y salida apuntan a dim_fecha en papeles distintos. Ninguna
-- reserva se pierde por falta de dato: las claves sin pareja van al miembro desconocido (−1).
with r as (select * from {{ ref('int_reservas') }}),

grupos as (
    select
        huesped_id,
        huesped_golden_id
    from {{ ref('int_huespedes_grupos') }}
),

fichas as (
    select
        huesped_id,
        pais_codigo,
        anio_nacimiento
    from {{ ref('stg_pms__huespedes') }}
),

miembros as (
    select
        g.huesped_golden_id,
        min(m.alta_en) as alta_en
    from {{ ref('stg_pms__miembros_fidelizacion') }} as m
    inner join grupos as g on m.huesped_id = g.huesped_id
    group by g.huesped_golden_id
),

depositos as (
    select distinct reserva_id
    from {{ ref('stg_pms__pagos') }}
    where tipo_pago = 'deposito'
),

base as (
    select
        r.*,
        coalesce(g.huesped_golden_id, -1) as huesped_golden_id,
        f.pais_codigo,
        f.anio_nacimiento,
        coalesce(m.alta_en <= r.reservada_en, false) as es_miembro_programa,
        d.reserva_id is not null as con_deposito,
        coalesce(v.ingreso_reventa_eur, 0) as ingreso_reventa_eur
    from r
    left join grupos as g on r.huesped_id = g.huesped_id
    left join fichas as f on r.huesped_id = f.huesped_id
    left join miembros as m on g.huesped_golden_id = m.huesped_golden_id
    left join depositos as d on r.reserva_id = d.reserva_id
    left join {{ ref('int_reventa') }} as v on r.reserva_id = v.reserva_id
),

-- Estancias finalizadas del titular con llegada anterior a la fecha de esta reserva.
previas as (
    select
        b.reserva_id,
        count(e.reserva_id) as estancias_previas
    from base as b
    left join {{ ref('fct_estancia_huesped') }} as e
        on b.huesped_golden_id = e.huesped_golden_id and b.fecha_reserva > e.fecha_llegada
    group by b.reserva_id
)

select
    b.reserva_id::bigint as reserva_id,
    b.localizador::text as localizador,
    coalesce(h.hotel_sk, -1)::bigint as hotel_sk,
    b.hotel_id::bigint as hotel_id,
    coalesce(c.canal_sk, -1)::bigint as canal_sk,
    b.canal_id::bigint as canal_id,
    b.tipo_canal::text as tipo_canal,
    b.es_directo,
    b.es_ota,
    coalesce(t.tarifa_sk, -1)::bigint as tarifa_sk,
    coalesce(hu.huesped_sk, -1)::bigint as huesped_sk,
    b.huesped_golden_id::bigint as huesped_golden_id,
    coalesce(p.perfil_sk, -1)::bigint as perfil_sk,
    (case when b.campana_id is null then -2 else coalesce(ca.campana_sk, -1) end)::bigint as campana_sk,
    coalesce(i.indicadores_sk, -1)::bigint as indicadores_sk,
    coalesce(me.mercado_sk, -1)::bigint as mercado_sk,
    b.tipo_habitacion_id::bigint as tipo_habitacion_id,
    b.fecha_reserva,
    b.fecha_llegada,
    b.fecha_salida,
    b.reservada_en,
    b.estado::text as estado,
    b.es_cancelada,
    b.es_cancelacion_cliente,
    b.es_reubicacion,
    b.fecha_cancelacion,
    b.noches::integer as noches,
    b.adultos::integer as adultos,
    b.ninos::integer as ninos,
    b.importe_total::numeric as importe_total,
    b.divisa::text as divisa,
    b.importe_total_eur::numeric as importe_total_eur,
    b.lead_time_dias::integer as lead_time_dias,
    b.importe_penalizacion_cliente::numeric as importe_penalizacion_cliente,
    b.ingreso_reventa_eur::numeric as ingreso_reventa_eur,
    b.tasa_comision::numeric as tasa_comision
from base as b
inner join previas as pr on b.reserva_id = pr.reserva_id
left join {{ ref('dim_hotel') }} as h
    on b.hotel_id = h.hotel_id and b.reservada_en >= h.valido_desde and b.reservada_en < h.valido_hasta
left join {{ ref('dim_canal') }} as c on b.canal_id = c.canal_id
left join {{ ref('dim_tarifa') }} as t on b.plan_tarifa_id = t.plan_tarifa_id
left join {{ ref('dim_huesped') }} as hu
    on
        b.huesped_golden_id = hu.huesped_golden_id
        and b.reservada_en >= hu.valido_desde
        and b.reservada_en < hu.valido_hasta
left join {{ ref('dim_perfil_huesped') }} as p
    on
        coalesce(hu.segmento, 'desconocido') = p.segmento
        and {{ banda_edad('b.anio_nacimiento', 'b.fecha_llegada') }} = p.banda_edad
        and b.es_miembro_programa = p.es_miembro_programa
        and {{ banda_estancias_previas('pr.estancias_previas') }} = p.banda_estancias_previas
left join {{ ref('dim_campana') }} as ca on b.campana_id = ca.campana_id
left join {{ ref('dim_indicadores_reserva') }} as i
    on
        b.es_reembolsable = i.es_reembolsable  -- sin plan de tarifa: desconocido (-1), no «no»
        and b.con_deposito = i.con_deposito
        and (b.campana_id is not null) = i.con_campana
        and (b.ninos > 0) = i.con_ninos
left join {{ ref('dim_mercado') }} as me on b.pais_codigo = me.pais_codigo
