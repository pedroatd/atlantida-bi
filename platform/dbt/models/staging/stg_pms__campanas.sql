select
    campaign_id as campana_id,
    code as codigo,
    name as nombre,
    {{ traducir('target_channel_type', {'direct': 'directo', 'ota': 'ota', 'tour_operator': 'turoperador', 'agency': 'agencia'}) }} as tipo_canal_objetivo,
    start_date as fecha_inicio,
    end_date as fecha_fin,
    budget as presupuesto,
    {{ columnas_tecnicas() }}
from {{ source('raw_pms', 'campaign') }}
