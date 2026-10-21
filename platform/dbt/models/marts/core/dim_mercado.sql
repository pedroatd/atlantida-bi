select
    {{ clave_sustituta(['pais_codigo']) }} as mercado_sk,
    pais_codigo,
    pais,
    mercado_istac
from {{ ref('paises') }}
union all
-- noqa: disable=AL03
-- Fila del miembro desconocido: las columnas toman el nombre de la primera consulta.
select
    -1,
    'N/D',
    'Desconocido',
    'OTROS'
