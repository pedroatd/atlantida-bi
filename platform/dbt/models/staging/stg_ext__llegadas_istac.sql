-- Llegadas de turistas por isla, mes y mercado emisor (ISTAC, FRONTUR-Canarias).
select
    isla,
    pais_origen as mercado_istac,
    llegadas,
    _loaded_at as cargado_en,
    to_date(periodo_mes || '-01', 'YYYY-MM-DD') as mes
from {{ source('raw_ext', 'istac_frontur') }}
