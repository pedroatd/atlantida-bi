-- Tipo de cambio de cada divisa para cada día (los fines de semana y festivos el BCE no publica:
-- vale el último publicado; antes del primer dato de la instantánea, el primero).
with tipos as (
    select
        fecha,
        divisa,
        unidades_por_euro
    from {{ ref('stg_ext__tipos_cambio') }}
),

reservas as (
    select fecha_reserva from {{ ref('stg_pms__reservas') }}
),

limites as (
    select
        least((select min(fecha) from tipos), (select min(fecha_reserva) from reservas)) as desde,
        greatest((select max(fecha) from tipos), (select max(fecha_reserva) from reservas)) as hasta
),

dias as (
    select
        v.divisa,
        d::date as fecha
    from (select distinct divisa from tipos) as v
    cross join limites as l
    cross join lateral generate_series(l.desde, l.hasta, interval '1 day') as d
),

marcados as (
    select
        d.divisa,
        d.fecha,
        t.unidades_por_euro,
        count(t.unidades_por_euro) over (partition by d.divisa order by d.fecha) as grupo
    from dias as d
    left join tipos as t on d.divisa = t.divisa and d.fecha = t.fecha
),

primeros as (
    select distinct on (divisa)
        divisa,
        unidades_por_euro as primero
    from tipos
    order by divisa, fecha
)

select
    m.divisa,
    m.fecha,
    coalesce(
        first_value(m.unidades_por_euro) over (partition by m.divisa, m.grupo order by m.fecha),
        p.primero
    ) as unidades_por_euro
from marcados as m
inner join primeros as p on m.divisa = p.divisa
