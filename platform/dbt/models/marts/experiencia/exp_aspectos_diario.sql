-- Direcciones de hotel: semáforo diario de los aspectos de las reseñas (vacío hasta que el módulo
-- de IA clasifique las reseñas).
select
    h.codigo as hotel,
    a.aspecto,
    a.fecha,
    a.menciones,
    a.sentimiento_medio,
    a.en_rojo
from {{ ref('int_aspectos_rojo_diario') }} as a
inner join {{ ref('dim_hotel_actual') }} as h on a.hotel_id = h.hotel_id
