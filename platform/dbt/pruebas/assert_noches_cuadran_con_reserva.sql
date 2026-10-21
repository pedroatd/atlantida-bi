{{ config(meta={'dagster': {'ref': {'name': 'fct_noche_estancia'}}}) }}
-- En Dagster, esta prueba es un check del asset fct_noche_estancia: tiene varios padres
-- y dagster-dbt no sabe a cuál unirla.
-- Conciliación entre hechos: en una estancia finalizada, las noches de fct_noche_estancia son las
-- de la reserva y su ingreso de alojamiento suma el importe de la reserva en euros (cada noche se
-- redondea al céntimo: tolerancia de un céntimo por noche). Solo cuentan las llegadas desde el
-- inicio del histórico: las reservas anteriores son historia de huéspedes (sirven para la
-- repetición) y no tienen auditoría nocturna. Devuelve las reservas que no cuadran.
with inicio as (
    select max(valor)::date as fecha
    from {{ ref('def_parametro') }}
    where clave = 'inicio_historico'
),

noches as (
    select
        reserva_id,
        count(*) as noches,
        sum(ingreso_habitacion) as ingreso
    from {{ ref('fct_noche_estancia') }}
    group by reserva_id
)

select
    r.reserva_id,
    r.noches,
    n.noches as noches_estancia,
    r.importe_total_eur,
    n.ingreso
from {{ ref('fct_reserva') }} as r
cross join inicio as i
left join noches as n on r.reserva_id = n.reserva_id
where
    r.estado = 'finalizada'
    and r.fecha_llegada >= i.fecha
    and (
        n.reserva_id is null
        or n.noches <> r.noches
        or abs(n.ingreso - r.importe_total_eur) > 0.01 * r.noches
    )
