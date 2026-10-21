-- La ocupación de un hotel en un día no puede superar el 100 % de las habitaciones disponibles.
select
    fecha,
    ambito,
    valor
from {{ ref('kpi_diario') }}
where kpi = 'ocupacion' and ambito <> 'CADENA' and valor > 1 + 1e-9
