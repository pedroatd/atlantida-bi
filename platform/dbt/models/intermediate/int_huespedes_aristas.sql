-- Pares de fichas (a < b) que coinciden en alguna clave, con las reglas que los unen.
select
    a.huesped_id as huesped_a,
    b.huesped_id as huesped_b,
    string_agg(distinct a.regla, ',' order by a.regla) as reglas
from {{ ref('int_huespedes_claves') }} as a
inner join {{ ref('int_huespedes_claves') }} as b
    on a.regla = b.regla and a.valor = b.valor and a.huesped_id < b.huesped_id
group by a.huesped_id, b.huesped_id
