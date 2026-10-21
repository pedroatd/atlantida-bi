select
    {{ clave_sustituta(['plan_tarifa_id']) }} as tarifa_sk,
    plan_tarifa_id,
    codigo,
    nombre,
    regimen_codigo,
    regimen,
    es_reembolsable,
    pct_deposito,
    pct_descuento
from {{ ref('stg_pms__planes_tarifa') }}
union all
-- noqa: disable=AL03
-- Fila del miembro desconocido: las columnas toman el nombre de la primera consulta.
select
    -1,
    -1,
    'N/D',
    'Desconocida',
    'N/D',
    'desconocido',
    null,
    null,
    null
