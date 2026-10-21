-- Identidad de los KPI hoteleros: RevPAR = ADR × ocupación (mismo periodo y ámbito). Los nulos no
-- se saltan: sin habitaciones disponibles, RevPAR y ocupación son nulos a la vez; sin noches
-- vendidas, el ADR es nulo y el RevPAR debe ser 0 (no puede haber ingreso sin noches).
with p as (
    select
        periodo_id,
        ambito,
        max(valor) filter (where kpi = 'revpar') as revpar,
        max(valor) filter (where kpi = 'adr') as adr,
        max(valor) filter (where kpi = 'ocupacion') as ocupacion
    from {{ ref('kpi_periodo') }}
    group by periodo_id, ambito
)

select *
from p
where
    abs(revpar - adr * ocupacion) > 1e-6 * greatest(1, abs(revpar))
    or (revpar is null) <> (ocupacion is null)
    or (adr is null and revpar <> 0)
