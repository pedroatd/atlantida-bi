-- Campañas de marketing. Dos filas especiales: −1 (desconocida) y −2 (sin campaña: no aplica).
select
    {{ clave_sustituta(['c.campana_id']) }} as campana_sk,
    c.campana_id,
    c.codigo,
    c.nombre,
    c.tipo_canal_objetivo,
    c.fecha_inicio,
    c.fecha_fin,
    c.presupuesto,
    (
        select string_agg(h.codigo, ', ' order by h.codigo)
        from {{ ref('stg_pms__campanas_hoteles') }} as ch
        inner join {{ ref('stg_pms__hoteles') }} as h on ch.hotel_id = h.hotel_id
        where ch.campana_id = c.campana_id
    ) as hoteles
from {{ ref('stg_pms__campanas') }} as c
union all
-- noqa: disable=AL03
-- Filas especiales: las columnas toman el nombre de la primera consulta.
select
    -1,
    -1,
    'N/D',
    'Desconocida',
    null,
    null,
    null,
    null,
    null
union all
select
    -2,
    -2,
    'SIN',
    'Sin campaña',
    null,
    null,
    null,
    null,
    null
