{{ config(materialized='materialized_view') }}
-- Vista materializada (concepto de agregados del cubo): el rendimiento mensual que más se consulta,
-- precalculado; cada build la deja actualizada. Lee kpi_periodo: no repite ninguna fórmula. El ámbito
-- '-1' (hechos sin hotel) no es un hotel y queda fuera. completo = false: el mes aún no ha madurado
-- (corte posterior a los datos) y sus cifras pueden cambiar; sin cierre contable, el GOPPAR es nulo.
select
    to_date(periodo_id, 'YYYY-MM') as mes,
    ambito,
    bool_and(completo) as completo,
    max(valor) filter (where kpi = 'ocupacion') as ocupacion,
    max(valor) filter (where kpi = 'adr') as adr,
    max(valor) filter (where kpi = 'revpar') as revpar,
    max(valor) filter (where kpi = 'trevpar') as trevpar,
    max(valor) filter (where kpi = 'goppar') as goppar,
    max(valor) filter (where kpi = 'mpi') as mpi,
    max(valor) filter (where kpi = 'ari') as ari,
    max(valor) filter (where kpi = 'rgi') as rgi,
    max(valor) filter (where kpi = 'ingreso_perdido_neto') as ingreso_perdido_neto,
    max(valor) filter (where kpi = 'lead_time_medio') as lead_time_medio,
    max(valor) filter (where kpi = 'estancia_media') as estancia_media
from {{ ref('kpi_periodo') }}
where tipo_periodo = 'mes' and ambito <> '-1'
group by periodo_id, ambito
