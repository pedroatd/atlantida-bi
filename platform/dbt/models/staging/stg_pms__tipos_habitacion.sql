select
    room_type_id as tipo_habitacion_id,
    hotel_id,
    code as codigo,
    name as nombre,
    capacity as capacidad,
    base_rate as tarifa_base,
    {{ columnas_tecnicas() }}
from {{ source('raw_pms', 'room_type') }}
