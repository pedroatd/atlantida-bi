{{ config(indexes=[{'columns': ['hotel_id', 'mes'], 'unique': True}]) }}
-- Tabla agregada (concepto de agregados del cubo): el mes por hotel precalculado, mucho más
-- pequeña que el detalle diario. Solo medidas aditivas; los KPI se calculan siempre al final.
select
    hotel_id,
    date_trunc('month', fecha)::date as mes,
    sum(habitaciones) as habitaciones_str,
    sum(disponibles) as habitaciones_disponibles,
    sum(noches_vendidas) as noches_vendidas,
    sum(noches_vendidas_directo) as noches_vendidas_directo,
    sum(ingreso_habitaciones) as ingreso_habitaciones
from {{ ref('fct_ocupacion_diaria') }}
group by hotel_id, date_trunc('month', fecha)
