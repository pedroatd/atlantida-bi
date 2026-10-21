-- Estancias finalizadas por huésped titular (golden record de la ficha de la reserva): base de la
-- tasa de repetición (solo titulares, aclaración de atlantida.yml 2.3.0; los acompañantes no
-- cuentan). Un huésped repite si tiene otra estancia con llegada en los 24 meses anteriores
-- (estrictamente antes). Una reserva cuyo titular no tiene ficha no entra: sin persona
-- identificada no hay repetición que medir.
with estancias as (
    select distinct
        r.reserva_id,
        g.huesped_golden_id,
        r.hotel_id,
        r.fecha_llegada
    from {{ ref('int_reservas') }} as r
    inner join {{ ref('int_huespedes_grupos') }} as g on r.huesped_id = g.huesped_id
    where r.estado = 'finalizada'
)

select
    reserva_id,
    huesped_golden_id,
    hotel_id,
    fecha_llegada,
    coalesce(
        max(fecha_llegada) over (
            partition by huesped_golden_id order by fecha_llegada
            range between unbounded preceding and interval '1 day' preceding
        ) >= fecha_llegada - interval '24 months',
        false
    ) as repite_24m
from estancias
