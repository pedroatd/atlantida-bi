select
    rate_plan_id as plan_tarifa_id,
    code as codigo,
    name as nombre,
    board as regimen_codigo,
    {{ traducir('board', {'RO': 'solo_alojamiento', 'BB': 'alojamiento_desayuno', 'HB': 'media_pension', 'FB': 'pension_completa', 'AI': 'todo_incluido'}) }} as regimen,
    refundable as es_reembolsable,
    deposit_pct as pct_deposito,
    discount_pct as pct_descuento,
    {{ columnas_tecnicas() }}
from {{ source('raw_pms', 'rate_plan') }}
