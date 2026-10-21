-- Cargos de folio (folio_charge): restauración, spa, minibar, excursiones y otros. Se imputan
-- por la fecha del servicio; dias_retraso mide cuánto tardó en anotarse.
select
    charge_id as cargo_id,
    reservation_id as reserva_id,
    posted_at as registrado_en,
    {{ fecha_local('posted_at') }} as fecha_registro,
    service_date as fecha_servicio,
    {{ traducir('department', {'fnb': 'restauracion', 'spa': 'spa', 'minibar': 'minibar', 'excursion': 'excursiones', 'other': 'otros'}) }} as departamento,
    amount as importe,
    {{ fecha_local('posted_at') }} - service_date as dias_retraso,
    {{ columnas_tecnicas() }}
from {{ source('raw_pms', 'folio_charge') }}
