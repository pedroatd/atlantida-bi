-- Revenue manager. Precio medio (ADR) por hotel, día y tipo de habitación frente al ADR del
-- compset del hotel ese día. indice_precio es el ARI (100 = paridad); nulo los días sin informe
-- del compset (huecos del proveedor). Fórmulas del documento de definición (formulas_kpi).
{%- set f = formulas_kpi() %}
with noches as (
    select
        n.fecha_estancia as fecha,
        n.hotel_id,
        coalesce(hab.tipo_codigo, '?') as tipo_habitacion,
        count(*)::numeric as noches_vendidas,
        sum(n.ingreso_habitacion)::numeric as ingreso_habitaciones
    from {{ ref('fct_noche_estancia') }} as n
    left join {{ ref('dim_habitacion') }} as hab on n.habitacion_sk = hab.habitacion_sk
    group by n.fecha_estancia, n.hotel_id, coalesce(hab.tipo_codigo, '?')
),

bases as (
    select
        n.fecha,
        coalesce(h.codigo, '-1') as hotel,
        n.tipo_habitacion,
        n.noches_vendidas,
        n.ingreso_habitaciones,
        c.adr_compset::numeric as adr_compset
    from noches as n
    left join {{ ref('dim_hotel_actual') }} as h on n.hotel_id = h.hotel_id
    left join {{ ref('fct_compset_diario') }} as c
        on n.hotel_id = c.hotel_id and n.fecha = c.fecha and c.tiene_dato
)

select
    fecha,
    hotel::text as hotel,
    tipo_habitacion::text as tipo_habitacion,
    noches_vendidas::integer as noches,
    ({{ f['adr'] }})::double precision as adr,
    adr_compset::double precision as adr_compset,
    ({{ f['ari'] }})::double precision as indice_precio
from bases
