-- Tras normalizar los dos formatos del proveedor, la ocupación del compset es un tanto por uno.
select
    hotel_id,
    fecha,
    ocupacion
from {{ ref('stg_ext__compset_diario') }}
where ocupacion < 0 or ocupacion > 1.2
