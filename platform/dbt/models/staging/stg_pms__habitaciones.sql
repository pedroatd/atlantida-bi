select
    room_id as habitacion_id,
    hotel_id,
    room_type_id as tipo_habitacion_id,
    room_number as numero,
    floor as planta,
    {{ traducir('status', {'active': 'activa'}) }} as estado,
    {{ columnas_tecnicas() }}
from {{ source('raw_pms', 'room') }}
