-- Reserva enriquecida: canal conformado, importe en euros (tipo BCE del día de la reserva),
-- antelación, cancelación (del cliente o reubicación del hotel) y tipo de comisión vigente. Una
-- reserva cuyo canal aún no está cargado no se pierde: queda sin tipo de canal (miembro -1 en los
-- hechos).
with reservas as (select * from {{ ref('stg_pms__reservas') }}),

canales as (select * from {{ ref('int_canales_conformados') }}),

planes as (
    select
        plan_tarifa_id,
        es_reembolsable
    from {{ ref('stg_pms__planes_tarifa') }}
),

cancelaciones as (
    select
        reserva_id,
        cancelada_en,
        fecha_cancelacion,
        es_reubicacion,
        importe_penalizacion
    from {{ ref('stg_pms__cancelaciones') }}
),

tipos as (
    select
        divisa,
        fecha,
        unidades_por_euro
    from {{ ref('int_tipos_cambio_diarios') }}
),

comisiones as (
    select
        canal_id,
        vigente_desde,
        tasa_comision
    from {{ ref('stg_pms__comisiones_canal') }}
)

select
    r.reserva_id,
    r.localizador,
    r.hotel_id,
    r.huesped_id,
    r.canal_id,
    c.canal_canonico_id,
    c.tipo_canal,
    coalesce(c.tipo_canal = 'directo', false) as es_directo,
    coalesce(c.tipo_canal = 'ota', false) as es_ota,
    r.plan_tarifa_id,
    p.es_reembolsable,
    r.tipo_habitacion_id,
    r.campana_id,
    r.reservada_en,
    r.fecha_reserva,
    r.fecha_llegada,
    r.fecha_salida,
    r.noches,
    r.adultos,
    r.ninos,
    r.estado,
    r.importe_total,
    r.divisa,
    case
        when r.divisa = 'EUR' then r.importe_total
        else r.importe_total / nullif(t.unidades_por_euro, 0)
    end as importe_total_eur,
    r.fecha_llegada - r.fecha_reserva as lead_time_dias,
    k.cancelada_en,
    k.fecha_cancelacion,
    k.reserva_id is not null as es_cancelada,
    coalesce(k.es_reubicacion, false) as es_reubicacion,
    k.reserva_id is not null and not k.es_reubicacion as es_cancelacion_cliente,
    case when k.reserva_id is not null and not k.es_reubicacion then k.importe_penalizacion else 0 end
        as importe_penalizacion_cliente,
    coalesce(
        (
            select m.tasa_comision from comisiones as m
            where m.canal_id = r.canal_id and m.vigente_desde <= r.fecha_reserva
            order by m.vigente_desde desc limit 1
        ),
        (
            select m.tasa_comision from comisiones as m
            where m.canal_id = c.canal_canonico_id and m.vigente_desde <= r.fecha_reserva
            order by m.vigente_desde desc limit 1
        ),
        0
    ) as tasa_comision,
    r.cargado_en,
    r.actualizado_en
from reservas as r
left join canales as c on r.canal_id = c.canal_id
left join planes as p on r.plan_tarifa_id = p.plan_tarifa_id
left join cancelaciones as k on r.reserva_id = k.reserva_id
left join tipos as t on r.divisa = t.divisa and r.fecha_reserva = t.fecha
