select
    campaign_id as campana_id,
    hotel_id,
    {{ columnas_tecnicas() }}
from {{ source('raw_pms', 'campaign_hotel') }}
