select
    channel_id as canal_id,
    valid_from as vigente_desde,
    valid_to as vigente_hasta,
    rate as tasa_comision,
    {{ columnas_tecnicas() }}
from {{ source('raw_pms', 'channel_commission') }}
