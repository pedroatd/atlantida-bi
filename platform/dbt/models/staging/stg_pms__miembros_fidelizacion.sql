select
    member_id as miembro_id,
    guest_id as huesped_id,
    program as programa,
    enrolled_at as alta_en,
    left_at as baja_en,
    {{ columnas_tecnicas() }}
from {{ source('raw_pms', 'loyalty_member') }}
