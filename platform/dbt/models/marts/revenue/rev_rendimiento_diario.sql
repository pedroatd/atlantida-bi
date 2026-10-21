-- Revenue manager: rendimiento diario de cada hotel y su posición frente al compset (MPI, ARI,
-- RGI). Fórmulas del documento de definición (formulas_kpi).
{%- set f = formulas_kpi() %}
with bases as (
    select
        o.hotel_id,
        h.codigo as hotel,
        o.fecha,
        o.disponibles::numeric as habitaciones_disponibles,
        o.habitaciones::numeric as habitaciones_disponibles_str,
        o.noches_vendidas::numeric as noches_vendidas,
        o.ingreso_habitaciones::numeric as ingreso_habitaciones,
        c.ocupacion_compset,
        c.adr_compset,
        c.revpar_compset
    from {{ ref('fct_ocupacion_diaria') }} as o
    inner join {{ ref('dim_hotel_actual') }} as h on o.hotel_id = h.hotel_id
    left join {{ ref('fct_compset_diario') }} as c on o.hotel_id = c.hotel_id and o.fecha = c.fecha
)

select
    hotel_id,
    hotel,
    fecha,
    ({{ f['ocupacion'] }})::double precision as ocupacion,
    ({{ f['adr'] }})::double precision as adr,
    ({{ f['revpar'] }})::double precision as revpar,
    ocupacion_compset,
    adr_compset,
    revpar_compset,
    ({{ f['mpi'] }})::double precision as mpi,
    ({{ f['ari'] }})::double precision as ari,
    ({{ f['rgi'] }})::double precision as rgi
from bases
