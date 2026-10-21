{{ config(meta={'dagster': {'ref': {'name': 'brg_reserva_huesped'}}}) }}
-- En Dagster, esta prueba es un check del asset brg_reserva_huesped: tiene varios padres
-- y dagster-dbt no sabe a cuál unirla.
-- El titular de la puente es la ficha que figura en la reserva (reservation.guest_id).
select b.reserva_id
from {{ ref('brg_reserva_huesped') }} as b
inner join {{ ref('stg_pms__reservas') }} as r on b.reserva_id = r.reserva_id
where b.es_titular and b.huesped_id <> r.huesped_id
