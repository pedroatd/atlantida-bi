-- Canal conformado (los códigos heredados apuntan a su canal canónico) con una jerarquía
-- irregular: Directo → canal; Intermediado → tipo de intermediario → canal. El directo no tiene
-- nivel intermedio (nivel_2 nulo); nivel_2_relleno repite el padre para agrupar sin huecos.
select
    {{ clave_sustituta(['canal_id']) }} as canal_sk,
    canal_id,
    codigo_origen,
    canal_canonico_id,
    codigo,
    nombre,
    tipo_canal,
    es_codigo_heredado,
    case when tipo_canal = 'directo' then 'Directo' else 'Intermediado' end as nivel_1,
    case tipo_canal
        when 'ota' then 'Agencia en línea (OTA)'
        when 'turoperador' then 'Turoperador'
        when 'agencia' then 'Agencia de viajes'
    end as nivel_2,
    case tipo_canal
        when 'ota' then 'Agencia en línea (OTA)'
        when 'turoperador' then 'Turoperador'
        when 'agencia' then 'Agencia de viajes'
        else 'Directo'
    end as nivel_2_relleno,
    nombre as nivel_3
from {{ ref('int_canales_conformados') }}
union all
-- noqa: disable=AL03
-- Fila del miembro desconocido: las columnas toman el nombre de la primera consulta.
select
    -1,
    -1,
    'N/D',
    -1,
    'N/D',
    'Desconocido',
    'desconocido',
    false,
    'Desconocido',
    null,
    'Desconocido',
    'Desconocido'
