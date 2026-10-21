-- Tarifas publicadas por cada competidor (rate shopper), en los dos formatos del proveedor.
select
    competidor,
    fecha_estancia,
    fecha_consulta,
    replace(tarifa, ',', '.')::numeric as tarifa,
    coalesce(tarifa like '%,%', false) as formato_alternativo
from {{ source('raw_ext', 'rate_shopper') }}
