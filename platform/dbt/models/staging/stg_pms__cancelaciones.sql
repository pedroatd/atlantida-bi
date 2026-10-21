-- Cancelaciones (cancellation). Las reubicaciones por falta de habitación (el motivo empieza por
-- «Reubicación») son del hotel, no del cliente: se marcan para no contarlas como cancelaciones.
select
    cancellation_id as cancelacion_id,
    reservation_id as reserva_id,
    cancelled_at as cancelada_en,
    {{ fecha_local('cancelled_at') }} as fecha_cancelacion,
    reason as motivo,
    penalty_amount as importe_penalizacion,
    -- sin distinguir mayúsculas, tildes ni espacios iniciales; sin motivo, no es reubicación
    coalesce({{ sin_tildes('trim(normalize(reason, nfc))') }} like 'reubicacion%', false) as es_reubicacion,
    {{ columnas_tecnicas() }}
from {{ source('raw_pms', 'cancellation') }}
