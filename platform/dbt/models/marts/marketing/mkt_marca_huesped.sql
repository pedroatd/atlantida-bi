-- Marketing y direcciones de hotel. Marcas de huésped del PMS (guest_flag) sobre el golden
-- record: las del histórico del simulador y las que escribe el reverse ETL del almacén
-- (marcada_por empieza por «almacen:»). Solo ids seudónimos.
select
    g.huesped_golden_id,
    m.huesped_id,
    m.marca::text as marca,
    m.marcada_en,
    m.marcada_por::text as marcada_por
from {{ ref('stg_pms__marcas_huesped') }} as m
left join {{ ref('int_huespedes_grupos') }} as g on m.huesped_id = g.huesped_id
