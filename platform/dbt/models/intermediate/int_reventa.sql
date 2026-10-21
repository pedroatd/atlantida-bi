-- Ingreso de reventa (supuesto S17 de atlantida.yml): noches que libera una cancelación del cliente
-- y que vende después otra reserva del mismo hotel, tipo de habitación y fecha, con el límite del
-- ingreso cancelado de esa noche. Solo hay reventa si la cancelación desplazó demanda: esa noche
-- el tipo de habitación se llenó (noches vendidas >= habitaciones disponibles de ese tipo, sin
-- las bloqueadas; con sobreventa, más). En una noche que no se llenó, la venta posterior es
-- demanda ordinaria y lo cancelado sigue perdido.
-- Regla de emparejamiento, por orden de llegada en cada celda llena (hotel, tipo, fecha): cada venta
-- repone la noche liberada más antigua que siga sin reponer en el instante de la venta (una venta
-- del mismo instante que la cancelación no la repone); como mucho se reponen tantas noches como
-- habitaciones disponibles. Cada noche liberada se repone una sola vez y cada noche vendida repone
-- una sola liberada.
--
-- Cálculo sin bucles: si la venta i-ésima de la celda (por instante) ve C(i) cancelaciones
-- anteriores, las reposiciones hechas hasta ella son R(i) = i + min(0, min_{j<=i} (C(j) - j)).
-- La venta i repone algo si R(i) > R(i-1), y lo que repone es la cancelación R(i)-ésima.
with canceladas as (
    select
        r.reserva_id,
        r.hotel_id,
        r.tipo_habitacion_id,
        r.cancelada_en,
        n::date as fecha,
        r.importe_total_eur / nullif(r.noches, 0) as ingreso_noche
    from {{ ref('int_reservas') }} as r
    cross join lateral generate_series(r.fecha_llegada, r.fecha_salida - 1, interval '1 day') as n
    where r.es_cancelacion_cliente
),

celdas_con_cancelacion as (
    select distinct
        hotel_id,
        tipo_habitacion_id,
        fecha
    from canceladas
),

habitaciones_tipo as (
    select
        hotel_id,
        tipo_habitacion_id,
        count(*) as habitaciones
    from {{ ref('stg_pms__habitaciones') }}
    group by hotel_id, tipo_habitacion_id
),

bloqueadas_tipo as (
    select
        c.hotel_id,
        c.tipo_habitacion_id,
        c.fecha,
        count(distinct b.habitacion_id) as bloqueadas
    from celdas_con_cancelacion as c
    inner join {{ ref('stg_pms__habitaciones') }} as h
        on c.hotel_id = h.hotel_id and c.tipo_habitacion_id = h.tipo_habitacion_id
    inner join {{ ref('stg_pms__bloqueos') }} as b
        on h.habitacion_id = b.habitacion_id and c.fecha between b.fecha_inicio and b.fecha_fin
    group by c.hotel_id, c.tipo_habitacion_id, c.fecha
),

vendidas_celda as (
    select
        r.hotel_id,
        r.tipo_habitacion_id,
        n.fecha_estancia as fecha,
        count(*) as vendidas
    from {{ ref('stg_pms__noches') }} as n
    inner join {{ ref('int_reservas') }} as r on n.reserva_id = r.reserva_id
    inner join celdas_con_cancelacion as c
        on
            r.hotel_id = c.hotel_id
            and r.tipo_habitacion_id = c.tipo_habitacion_id
            and n.fecha_estancia = c.fecha
    group by r.hotel_id, r.tipo_habitacion_id, n.fecha_estancia
),

-- Celdas que se llenaron, con sus habitaciones disponibles.
celdas as (
    select
        v.hotel_id,
        v.tipo_habitacion_id,
        v.fecha,
        t.habitaciones - coalesce(b.bloqueadas, 0) as disponibles
    from vendidas_celda as v
    inner join habitaciones_tipo as t
        on v.hotel_id = t.hotel_id and v.tipo_habitacion_id = t.tipo_habitacion_id
    left join bloqueadas_tipo as b
        on
            v.hotel_id = b.hotel_id
            and v.tipo_habitacion_id = b.tipo_habitacion_id
            and v.fecha = b.fecha
    where v.vendidas >= t.habitaciones - coalesce(b.bloqueadas, 0)
),

canceladas_orden as (
    select
        c.*,
        k.disponibles,
        row_number() over (
            partition by c.hotel_id, c.tipo_habitacion_id, c.fecha order by c.cancelada_en, c.reserva_id
        ) as orden
    from canceladas as c
    inner join celdas as k
        on c.hotel_id = k.hotel_id and c.tipo_habitacion_id = k.tipo_habitacion_id and c.fecha = k.fecha
),

ventas as (
    select
        n.noche_id,
        r.hotel_id,
        r.tipo_habitacion_id,
        n.fecha_estancia as fecha,
        r.reservada_en,
        n.ingreso_habitacion
    from {{ ref('stg_pms__noches') }} as n
    inner join {{ ref('int_reservas') }} as r on n.reserva_id = r.reserva_id
    inner join celdas as c
        on
            r.hotel_id = c.hotel_id
            and r.tipo_habitacion_id = c.tipo_habitacion_id
            and n.fecha_estancia = c.fecha
),

-- Cancelaciones y ventas de cada celda en una sola secuencia. En el mismo instante va antes la
-- venta: así no cuenta la cancelación simultánea.
eventos as (
    select
        hotel_id,
        tipo_habitacion_id,
        fecha,
        cancelada_en as instante,
        1 as es_cancelacion,
        null::bigint as noche_id,
        null::numeric as ingreso_habitacion
    from canceladas_orden
    union all
    select
        hotel_id,
        tipo_habitacion_id,
        fecha,
        reservada_en as instante,
        0 as es_cancelacion,
        noche_id,
        ingreso_habitacion
    from ventas
),

acumulados as (
    select
        *,
        sum(es_cancelacion) over (
            partition by hotel_id, tipo_habitacion_id, fecha
            order by instante, es_cancelacion, noche_id
            rows between unbounded preceding and current row
        ) as canceladas_antes
    from eventos
),

ventas_numeradas as (
    select
        *,
        row_number() over (
            partition by hotel_id, tipo_habitacion_id, fecha order by instante, noche_id
        ) as i
    from acumulados
    where es_cancelacion = 0
),

holguras as (
    select
        *,
        min(canceladas_antes - i) over (
            partition by hotel_id, tipo_habitacion_id, fecha
            order by instante, noche_id
            rows between unbounded preceding and current row
        ) as holgura
    from ventas_numeradas
),

reposiciones as (
    select
        *,
        i + least(0, holgura) as repuestas
    from holguras
),

emparejadas as (
    select
        *,
        lag(repuestas, 1, 0::bigint) over (
            partition by hotel_id, tipo_habitacion_id, fecha order by instante, noche_id
        ) as repuestas_antes
    from reposiciones
)

select
    c.reserva_id,
    sum(least(v.ingreso_habitacion, c.ingreso_noche)) as ingreso_reventa_eur,
    count(*) as noches_revendidas
from canceladas_orden as c
inner join emparejadas as v
    on
        c.hotel_id = v.hotel_id
        and c.tipo_habitacion_id = v.tipo_habitacion_id
        and c.fecha = v.fecha
        and c.orden = v.repuestas
where v.repuestas > v.repuestas_antes and c.orden <= c.disponibles
group by c.reserva_id
