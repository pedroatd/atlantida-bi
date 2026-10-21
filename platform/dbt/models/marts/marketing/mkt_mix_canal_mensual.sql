-- Marketing: mezcla de canales (noches por fecha de estancia) por mes y hotel, por la jerarquía
-- del canal; peso_en_noches es la parte de las noches del hotel y mes que aporta cada canal.
with canales as (
    select
        date_trunc('month', n.fecha_estancia)::date as mes,
        h.codigo as hotel,
        c.nivel_1,
        c.nivel_2_relleno,
        c.codigo as canal,
        c.tipo_canal,
        count(*) as noches,
        sum(n.ingreso_habitacion) as ingreso_habitaciones,
        sum(n.comision) as comisiones
    from {{ ref('fct_noche_estancia') }} as n
    inner join {{ ref('dim_canal') }} as c on n.canal_sk = c.canal_sk
    inner join {{ ref('dim_hotel_actual') }} as h on n.hotel_id = h.hotel_id
    group by 1, 2, 3, 4, 5, 6
)

select
    mes,
    hotel,
    nivel_1,
    nivel_2_relleno,
    canal,
    tipo_canal,
    noches,
    ingreso_habitaciones,
    comisiones,
    -- reparto descriptivo, no es KPI: peso del canal en las noches del hotel y mes (no está en la definición)
    noches::double precision / sum(noches) over (partition by mes, hotel) as peso_en_noches
from canales
