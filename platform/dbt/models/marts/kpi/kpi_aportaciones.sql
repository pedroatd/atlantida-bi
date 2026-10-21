{{ config(materialized='view') }}
-- Aportación diaria de cada hecho a cada métrica base aditiva, por hotel (código): la lee el
-- cálculo del impacto de las acciones (atlantida-accion) para medir un KPI en cualquier ventana y
-- con la madurez de las reservas netas (valida_hasta = fecha de cancelación). Vista: no duplica
-- datos; bi_reader la lee sin acceso a intermediate.
select
    a.fecha,
    coalesce(h.codigo, '-1') as hotel,
    a.metrica,
    a.valida_hasta,
    a.valor
from {{ ref('int_kpi_aportaciones_diarias') }} as a
left join {{ ref('dim_hotel_actual') }} as h on a.hotel_id = h.hotel_id
