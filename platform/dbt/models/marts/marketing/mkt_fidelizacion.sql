-- Marketing (acción A3). Pertenencia al programa de fidelización por huésped del golden record:
-- primera alta y baja (nula si alguna ficha sigue en el programa). Solo ids seudónimos.
select
    g.huesped_golden_id,
    min(m.alta_en) as alta_en,
    case when bool_or(m.baja_en is null) then null else max(m.baja_en) end as baja_en
from {{ ref('stg_pms__miembros_fidelizacion') }} as m
inner join {{ ref('int_huespedes_grupos') }} as g on m.huesped_id = g.huesped_id
group by g.huesped_golden_id
