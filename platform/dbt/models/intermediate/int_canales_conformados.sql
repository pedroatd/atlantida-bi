-- Canales conformados: un código que no cumple el formato del catálogo (mayúsculas y dígitos)
-- se asigna al canal con el mismo nombre normalizado que sí lo cumple, y toma su tipo de canal.
-- Regla genérica: no depende de ningún código concreto.
with canales as (
    select
        canal_id,
        codigo,
        nombre,
        tipo_canal,
        codigo ~ '^[A-Z0-9]+$' as cumple_formato,
        regexp_replace(nombre, '\s*\(.*\)\s*', '', 'g') as nombre_sin_parentesis
    from {{ ref('stg_pms__canales') }}
),

normalizados as (
    select
        *,
        regexp_replace({{ sin_tildes('nombre_sin_parentesis') }}, '[^a-z0-9]', '', 'g') as nombre_normalizado
    from canales
),

canonicos as (
    select distinct on (nombre_normalizado)
        nombre_normalizado,
        canal_id as canal_canonico_id,
        codigo as codigo_canonico,
        nombre as nombre_canonico,
        tipo_canal as tipo_canal_canonico
    from normalizados
    where cumple_formato
    order by nombre_normalizado, canal_id
)

select
    n.canal_id,
    n.codigo as codigo_origen,
    n.nombre as nombre_origen,
    n.tipo_canal as tipo_canal_origen,
    n.cumple_formato,
    coalesce(k.canal_canonico_id, n.canal_id) as canal_canonico_id,
    coalesce(k.codigo_canonico, n.codigo) as codigo,
    coalesce(k.nombre_canonico, n.nombre) as nombre,
    coalesce(k.tipo_canal_canonico, n.tipo_canal) as tipo_canal,
    coalesce(k.canal_canonico_id, n.canal_id) <> n.canal_id as es_codigo_heredado
from normalizados as n
left join canonicos as k on n.nombre_normalizado = k.nombre_normalizado
