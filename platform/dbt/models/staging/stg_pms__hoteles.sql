-- Hoteles del PMS (hotel): nombres en español y tipología traducida.
select
    hotel_id,
    code as codigo,
    name as nombre,
    island as isla,
    municipality as municipio,
    {{ traducir('hotel_type', {'urban': 'urbano', 'resort': 'vacacional', 'all_inclusive': 'todo_incluido', 'rural': 'rural'}) }} as tipo_hotel,
    stars as estrellas,
    opened_on as fecha_apertura,
    {{ columnas_tecnicas() }}
from {{ source('raw_pms', 'hotel') }}
