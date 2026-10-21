-- Golden record (estado actual): reglas de supervivencia por atributo. País y año de nacimiento:
-- el valor más frecuente del grupo; segmento: el de la ficha actualizada más recientemente;
-- documento y contacto: basta con que una ficha lo tenga; alta: la primera del grupo.
select
    g.huesped_golden_id,
    count(*) as num_fichas,
    mode() within group (order by h.pais_codigo) as pais_codigo,
    mode() within group (order by h.anio_nacimiento) as anio_nacimiento,
    (array_agg(h.segmento order by h.actualizado_en desc, h.huesped_id desc))[1] as segmento_actual,
    bool_or(h.tiene_documento) as tiene_documento,
    bool_or(h.tiene_email or h.tiene_telefono) as es_contactable,
    min(h.creado_en) as primera_alta
from {{ ref('int_huespedes_grupos') }} as g
inner join {{ ref('stg_pms__huespedes') }} as h on g.huesped_id = h.huesped_id
group by g.huesped_golden_id
