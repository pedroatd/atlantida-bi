-- No se pueden vender más noches que habitaciones tiene el hotel. Se compara con el inventario
-- completo (base STR, `habitaciones`), no con las disponibles: una habitación bloqueada puede
-- tener una noche vendida antes del bloqueo.
select
    hotel_id,
    fecha,
    noches_vendidas,
    habitaciones
from {{ ref('fct_ocupacion_diaria') }}
where noches_vendidas > habitaciones
