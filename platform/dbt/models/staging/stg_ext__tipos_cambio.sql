-- Tipos de cambio de referencia del BCE: unidades de cada divisa por euro.
select
    fecha,
    divisa,
    tipo_cambio as unidades_por_euro
from {{ source('raw_ext', 'bce_tipos') }}
