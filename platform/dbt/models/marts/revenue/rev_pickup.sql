-- Revenue manager: pickup de cada día de corte (noches netas captadas en los 7 días anteriores
-- para estancias posteriores al corte).
{%- set f = formulas_kpi() %}
with cortes as (
    select d.fecha as corte
    from {{ ref('dim_fecha') }} as d
    where
        d.fecha between (select min(o.fecha) from {{ ref('fct_ocupacion_diaria') }} as o)
        and (select max(o.fecha) from {{ ref('fct_ocupacion_diaria') }} as o)
),

captadas as (
    select
        c.corte,
        r.hotel_id,
        sum(greatest(0, r.fecha_salida - greatest(r.fecha_llegada, c.corte + 1))) as noches
    from cortes as c
    inner join {{ ref('fct_reserva') }} as r on c.corte - 7 < r.fecha_reserva and c.corte >= r.fecha_reserva
    group by c.corte, r.hotel_id
),

canceladas as (
    select
        c.corte,
        r.hotel_id,
        sum(greatest(0, r.fecha_salida - greatest(r.fecha_llegada, c.corte + 1))) as noches
    from cortes as c
    inner join {{ ref('fct_reserva') }} as r
        on c.corte - 7 < r.fecha_cancelacion and c.corte >= r.fecha_cancelacion
    group by c.corte, r.hotel_id
),

bases as (
    select
        coalesce(a.corte, k.corte) as corte,
        coalesce(a.hotel_id, k.hotel_id) as hotel_id,
        coalesce(a.noches, 0)::numeric as noches_captadas_ventana,
        coalesce(k.noches, 0)::numeric as noches_canceladas_ventana
    from captadas as a
    full join canceladas as k on a.corte = k.corte and a.hotel_id = k.hotel_id
)

select
    b.corte,
    h.codigo as hotel,
    b.noches_captadas_ventana,
    b.noches_canceladas_ventana,
    ({{ f['pickup'] }})::double precision as pickup
from bases as b
inner join {{ ref('dim_hotel_actual') }} as h on b.hotel_id = h.hotel_id
