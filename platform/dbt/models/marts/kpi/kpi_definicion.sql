-- Nombre, unidad, sentido, propietario, latencia y fórmula de cada KPI (de atlantida.yml), legibles
-- en marts_kpi para quien no lee staging.
select
    kpi,
    nombre,
    unidad,
    sentido,
    propietario,
    latencia,
    formula,
    en_capa_semantica
from {{ ref('def_kpi') }}
