-- Rachas de días seguidos en rojo de cada aspecto y hotel (islas de días consecutivos).
with marcados as (
    select
        hotel_id,
        aspecto,
        fecha,
        fecha - (row_number() over (partition by hotel_id, aspecto order by fecha))::int as isla
    from {{ ref('int_aspectos_rojo_diario') }}
    where en_rojo
)

select
    hotel_id,
    aspecto,
    min(fecha) as inicio,
    max(fecha) as fin,
    count(*) as dias
from marcados
group by hotel_id, aspecto, isla
