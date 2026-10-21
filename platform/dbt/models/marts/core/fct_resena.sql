-- Reseñas: el NPS sale de la pregunta de recomendación (0-10): promotores 9-10, detractores 0-6.
-- Las versiones del hotel y del huésped son las vigentes al publicarse la reseña.
select
    s.resena_id,
    s.reserva_id,
    coalesce(h.hotel_sk, -1) as hotel_sk,
    s.hotel_id,
    coalesce(c.canal_sk, -1) as canal_sk,
    coalesce(hu.huesped_sk, -1) as huesped_sk,
    s.fecha_publicacion,
    s.fuente,
    s.puntuacion,
    s.recomendacion,
    s.recomendacion >= 9 as es_promotor,
    s.recomendacion <= 6 as es_detractor,
    s.recomendacion is not null as tiene_recomendacion
from {{ ref('stg_pms__resenas') }} as s
left join {{ ref('int_reservas') }} as r on s.reserva_id = r.reserva_id
left join {{ ref('int_huespedes_grupos') }} as g on r.huesped_id = g.huesped_id
left join {{ ref('dim_hotel') }} as h
    on s.hotel_id = h.hotel_id and s.publicada_en >= h.valido_desde and s.publicada_en < h.valido_hasta
left join {{ ref('dim_canal') }} as c on r.canal_id = c.canal_id
left join {{ ref('dim_huesped') }} as hu
    on
        g.huesped_golden_id = hu.huesped_golden_id
        and s.publicada_en >= hu.valido_desde
        and s.publicada_en < hu.valido_hasta
