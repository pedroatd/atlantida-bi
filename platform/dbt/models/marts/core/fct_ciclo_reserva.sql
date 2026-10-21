-- Snapshot acumulativo: una fila por reserva con las fechas de sus hitos (reserva, primer pago,
-- cancelación, primera y última noche, salida). Se reconstruye en cada build con el estado
-- actual. Las reservas con llegada anterior al inicio del histórico son historia de huéspedes y
-- no tienen noches ni pagos (ciclo truncado por diseño). La cancelación es un hito terminal
-- (cancelada = true con fecha_cancelacion), igual que la finalización: una reserva cancelada no
-- queda como pendiente. versiones_registradas cuenta los estados distintos que guardó el
-- snapshot SCD2.
with noches as (
    select
        reserva_id,
        min(fecha_estancia) as primera,
        max(fecha_estancia) as ultima
    from {{ ref('stg_pms__noches') }}
    group by reserva_id
),

pagos as (
    select
        reserva_id,
        min(fecha_pago) as primer_pago
    from {{ ref('stg_pms__pagos') }}
    group by reserva_id
),

versiones as (
    select
        reserva_id,
        count(*) as versiones
    from {{ ref('snp_reservas') }}
    group by reserva_id
)

select
    r.reserva_id,
    r.hotel_sk,
    r.canal_sk,
    r.fecha_reserva,
    p.primer_pago as fecha_primer_pago,
    r.fecha_cancelacion,
    r.fecha_llegada,
    n.primera as fecha_primera_noche,
    n.ultima as fecha_ultima_noche,
    case when r.estado = 'finalizada' then r.fecha_salida end as fecha_salida_efectiva,
    r.estado as estado_actual,
    r.estado = 'cancelada' as cancelada,
    r.fecha_llegada - r.fecha_reserva as dias_reserva_a_llegada,
    r.fecha_cancelacion - r.fecha_reserva as dias_reserva_a_cancelacion,
    1 + (p.primer_pago is not null)::int + (n.primera is not null)::int + (r.estado in ('finalizada', 'cancelada'))::int
        as hitos_alcanzados,
    coalesce(v.versiones, 1) as versiones_registradas
from {{ ref('fct_reserva') }} as r
left join noches as n on r.reserva_id = n.reserva_id
left join pagos as p on r.reserva_id = p.reserva_id
left join versiones as v on r.reserva_id = v.reserva_id
