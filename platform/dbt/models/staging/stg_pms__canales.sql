select
    channel_id as canal_id,
    code as codigo,
    name as nombre,
    {{ traducir('channel_type', {'direct': 'directo', 'ota': 'ota', 'tour_operator': 'turoperador', 'agency': 'agencia'}) }} as tipo_canal,
    {{ columnas_tecnicas() }}
from {{ source('raw_pms', 'channel') }}
