-- Reglas comerciales devueltas al PMS (reverse ETL): rate_restriction.
select
    hotel_id,
    channel_id as canal_id,
    rate_plan_id as plan_tarifa_id,
    from_date as fecha_desde,
    to_date as fecha_hasta,
    rule as regla,
    parametro,
    set_at as fijada_en,
    set_by as fijada_por,
    {{ columnas_tecnicas() }}
from {{ source('raw_pms', 'rate_restriction') }}
