-- Los factores de ponderación de cada reserva suman 1 (si no, sumar por huésped infla o pierde
-- reservas).
select
    reserva_id,
    sum(factor_ponderacion) as total
from {{ ref('brg_reserva_huesped') }}
group by reserva_id
having abs(sum(factor_ponderacion) - 1) > 1e-9
