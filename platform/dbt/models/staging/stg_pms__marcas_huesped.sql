-- Marcas que el almacén devuelve al PMS (reverse ETL): guest_flag.
select
    guest_id as huesped_id,
    flag as marca,
    reason as motivo,
    set_at as marcada_en,
    set_by as marcada_por,
    {{ columnas_tecnicas() }}
from {{ source('raw_pms', 'guest_flag') }}
