select
    fecha,
    ambito,
    pais,
    nombre
from {{ source('raw_ext', 'festivos') }}
