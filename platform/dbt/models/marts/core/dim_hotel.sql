-- Hotel con historia (SCD2) a partir del snapshot. La primera versión vale desde 1900-01-01 para
-- que ningún hecho anterior al primer snapshot se quede sin versión (convención de Kimball).
with versiones as (
    select
        *,
        row_number() over (partition by hotel_id order by dbt_valid_from) as n
    from {{ ref('snp_hoteles') }}
)

select
    {{ clave_sustituta(['hotel_id', 'dbt_valid_from']) }} as hotel_sk,
    hotel_id,
    codigo,
    nombre,
    isla,
    municipio,
    tipo_hotel,
    estrellas,
    case when n = 1 then '1900-01-01 00:00:00+00'::timestamptz else dbt_valid_from end as valido_desde,
    dbt_valid_to as valido_hasta,
    dbt_valid_to = '9999-12-31 00:00:00+00'::timestamptz as es_actual
from versiones
union all
-- noqa: disable=AL03
-- Fila del miembro desconocido: las columnas toman el nombre de la primera consulta.
select
    -1,
    -1,
    'N/D',
    'Desconocido',
    'Desconocida',
    'Desconocido',
    'desconocido',
    null,
    '1900-01-01 00:00:00+00'::timestamptz,
    '9999-12-31 00:00:00+00'::timestamptz,
    true
