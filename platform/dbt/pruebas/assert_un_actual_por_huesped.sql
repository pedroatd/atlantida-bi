{{ config(meta={'dagster': {'ref': {'name': 'dim_huesped'}}}) }}
-- En Dagster, esta prueba es un check del asset dim_huesped: tiene varios padres
-- y dagster-dbt no sabe a cuál unirla.
-- Cada golden record tiene exactamente una versión vigente en dim_huesped.
select
    g.huesped_golden_id,
    count(d.huesped_sk) as actuales
from {{ ref('int_huesped_golden') }} as g
left join {{ ref('dim_huesped') }} as d
    on g.huesped_golden_id = d.huesped_golden_id and d.es_actual
group by g.huesped_golden_id
having count(d.huesped_sk) <> 1
