select
    cost_id as coste_id,
    hotel_id,
    cost_date as fecha_coste,
    {{ traducir('category', {'staff': 'personal', 'energy': 'energia', 'maintenance': 'mantenimiento', 'fnb_cost': 'coste_restauracion', 'marketing': 'marketing', 'other': 'otros'}) }} as categoria,
    amount as importe,
    {{ columnas_tecnicas() }}
from {{ source('raw_pms', 'cost_entry') }}
