-- Grano de kpi_metricas_base: una fila por periodo, ámbito y métrica.
select
    periodo_id,
    ambito,
    metrica,
    count(*) as filas
from {{ ref('kpi_metricas_base') }}
group by periodo_id, ambito, metrica
having count(*) > 1
