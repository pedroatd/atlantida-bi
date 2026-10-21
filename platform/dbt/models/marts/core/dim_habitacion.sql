select
    {{ clave_sustituta(['h.habitacion_id']) }} as habitacion_sk,
    h.habitacion_id,
    h.hotel_id,
    h.numero,
    h.planta,
    h.tipo_habitacion_id,
    t.codigo as tipo_codigo,
    t.nombre as tipo_nombre,
    t.capacidad,
    t.tarifa_base
from {{ ref('stg_pms__habitaciones') }} as h
inner join {{ ref('stg_pms__tipos_habitacion') }} as t on h.tipo_habitacion_id = t.tipo_habitacion_id
union all
-- noqa: disable=AL03
-- Fila del miembro desconocido: las columnas toman el nombre de la primera consulta.
select
    -1,
    -1,
    -1,
    'N/D',
    null,
    -1,
    'N/D',
    'Desconocida',
    null,
    null
