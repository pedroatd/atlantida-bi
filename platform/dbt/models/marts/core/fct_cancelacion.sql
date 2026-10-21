-- Una fila por cancelación. Las reubicaciones (el hotel deja sin habitación al cliente) se
-- conservan marcadas con es_reubicacion: no son cancelaciones del cliente y los KPI las excluyen.
-- La versión del hotel es la vigente en el instante de la cancelación.
select
    k.cancelacion_id,
    k.reserva_id,
    coalesce(h.hotel_sk, -1) as hotel_sk,
    r.hotel_id,
    coalesce(c.canal_sk, -1) as canal_sk,
    r.tipo_canal,
    k.fecha_cancelacion,
    r.fecha_llegada,
    r.fecha_llegada - k.fecha_cancelacion as dias_antelacion_cancelacion,
    k.es_reubicacion,
    k.motivo,
    k.importe_penalizacion,
    r.importe_total_eur as ingreso_cancelado_eur
from {{ ref('stg_pms__cancelaciones') }} as k
left join {{ ref('int_reservas') }} as r on k.reserva_id = r.reserva_id
left join {{ ref('dim_hotel') }} as h
    on r.hotel_id = h.hotel_id and k.cancelada_en >= h.valido_desde and k.cancelada_en < h.valido_hasta
left join {{ ref('dim_canal') }} as c on r.canal_id = c.canal_id
