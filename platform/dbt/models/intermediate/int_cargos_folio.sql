{{ config(materialized='view') }}
-- Cargos de folio con su hotel, marcados si se anotaron tarde o si son la repetición exacta de
-- otro cargo (misma reserva, instante, fecha de servicio, departamento e importe). Un cargo cuya
-- reserva aún no está cargada no se descarta (el hecho es incremental y no volvería): queda sin
-- hotel (miembro -1).
select
    c.cargo_id,
    c.reserva_id,
    r.hotel_id,
    c.registrado_en,
    c.fecha_registro,
    c.fecha_servicio,
    c.departamento,
    c.importe,
    c.dias_retraso,
    c.dias_retraso > {{ var('retraso_tardio_dias') }} as es_tardio,
    row_number() over (
        partition by c.reserva_id, c.registrado_en, c.fecha_servicio, c.departamento, c.importe
        order by c.cargo_id
    ) > 1 as es_repeticion,
    c.cargado_en
from {{ ref('stg_pms__cargos_folio') }} as c
left join {{ ref('stg_pms__reservas') }} as r on c.reserva_id = r.reserva_id
