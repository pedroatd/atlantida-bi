{{ config(meta={'dagster': {'ref': {'name': 'brg_reserva_huesped'}}}) }}
-- En Dagster, esta prueba es un check del asset brg_reserva_huesped: tiene varios padres
-- y dagster-dbt no sabe a cuál unirla.
-- La tabla puente tiene exactamente una fila por cada fila de reservation_guest: ningún huésped
-- (aunque no tenga ficha) se queda fuera del reparto.
select
    o.filas_origen,
    p.filas_puente
from (select count(*) as filas_origen from {{ ref('stg_pms__reservas_huespedes') }}) as o
cross join (select count(*) as filas_puente from {{ ref('brg_reserva_huesped') }}) as p
where o.filas_origen <> p.filas_puente
