-- Cada reserva tiene exactamente un titular en la tabla puente.
select
    reserva_id,
    count(*) filter (where es_titular) as titulares
from {{ ref('brg_reserva_huesped') }}
group by reserva_id
having count(*) filter (where es_titular) <> 1
