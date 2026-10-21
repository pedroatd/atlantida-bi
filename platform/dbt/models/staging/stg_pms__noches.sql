-- Noches de habitación ocupadas (stay_night): ingreso de alojamiento neto de IGIC en EUR.
select
    stay_night_id as noche_id,
    reservation_id as reserva_id,
    room_id as habitacion_id,
    stay_date as fecha_estancia,
    room_revenue as ingreso_habitacion,
    {{ columnas_tecnicas() }}
from {{ source('raw_pms', 'stay_night') }}
