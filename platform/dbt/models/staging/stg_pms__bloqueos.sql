-- Habitaciones fuera de servicio (room_block): no cuentan como disponibles esos días.
select
    block_id as bloqueo_id,
    room_id as habitacion_id,
    start_date as fecha_inicio,
    end_date as fecha_fin,
    reason as motivo,
    {{ columnas_tecnicas() }}
from {{ source('raw_pms', 'room_block') }}
