-- ml_writer (módulo de IA) lee el texto de las reseñas para clasificarlas; dbt reaplica el
-- permiso cada vez que recrea la vista.
{{ config(grants={'select': ['ml_writer']}) }}
select
    review_id as resena_id,
    reservation_id as reserva_id,
    hotel_id,
    source as fuente,
    posted_at as publicada_en,
    {{ fecha_local('posted_at') }} as fecha_publicacion,
    score as puntuacion,
    recommend as recomendacion,
    language as idioma,
    body as texto,
    {{ columnas_tecnicas() }}
from {{ source('raw_pms', 'review') }}
