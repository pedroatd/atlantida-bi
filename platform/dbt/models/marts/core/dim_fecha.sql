-- Dimensión fecha (un día por fila). Es también el time spine de MetricFlow y se usa en varios
-- papeles (fecha de reserva, de llegada, de estancia…: dimensión de rol). Su clave es la fecha:
-- las fechas de los hechos nunca faltan, así que no lleva fila «desconocida». El rango sale del
-- horizonte simulado de atlantida.yml: desde el 1 de enero del año anterior a la historia de
-- huéspedes (reservas hechas antes de llegar) hasta el 31 de diciembre de dos años después del fin
-- (reservas futuras). El calendario de festivos cubre menos años que el rango: fuera de su
-- cobertura, festivo_conocido es falso y los indicadores de festivos son nulos («sin dato»,
-- nunca «no es festivo»).
with horizonte as (
    select
        max(valor) filter (where clave = 'historia_huespedes_desde')::date as desde,
        max(valor) filter (where clave = 'fin_historico')::date as fin
    from {{ ref('def_parametro') }}
),

dias as (
    select d::date as fecha
    from horizonte
    cross join lateral generate_series(
        make_date(extract(year from desde)::int - 1, 1, 1)::timestamp,
        make_date(extract(year from fin)::int + 2, 12, 31)::timestamp,
        interval '1 day'
    ) as d
),

festivos as (
    select
        fecha,
        bool_or(ambito = 'nacional' and pais = 'ES') as es_festivo_nacional,
        bool_or(ambito = 'autonomico' and pais = 'ES') as es_festivo_canarias,
        string_agg(distinct split_part(ambito, ':', 2), ', ') filter (where ambito like 'insular:%')
            as festivo_insular_en,
        count(distinct pais) filter (where ambito = 'escolar') as mercados_en_vacaciones_escolares
    from {{ ref('stg_ext__festivos') }}
    group by fecha
),

cobertura as (
    select
        min(fecha) as desde,
        max(fecha) as hasta
    from {{ ref('stg_ext__festivos') }}
)

select
    d.fecha,
    extract(year from d.fecha)::int as anio,
    extract(quarter from d.fecha)::int as trimestre,
    extract(month from d.fecha)::int as mes,
    to_char(d.fecha, 'YYYY-MM') as anio_mes,
    (
        array[
            'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
            'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'
        ]
    )[extract(month from d.fecha)::int] as nombre_mes,
    extract(day from d.fecha)::int as dia_mes,
    extract(isodow from d.fecha)::int as dia_semana,
    (
        array['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']
    )[extract(isodow from d.fecha)::int] as nombre_dia,
    extract(isodow from d.fecha) >= 6 as es_fin_de_semana,
    extract(isoyear from d.fecha)::int as anio_iso,
    extract(week from d.fecha)::int as semana_iso,
    -- Temporada turística convencional de Canarias: invierno de noviembre a abril.
    case when extract(month from d.fecha) in (11, 12, 1, 2, 3, 4) then 'invierno' else 'verano' end
        as temporada_turistica,
    k.fecha_conocida as festivo_conocido,
    case when k.fecha_conocida then coalesce(f.es_festivo_nacional, false) end as es_festivo_nacional,
    case when k.fecha_conocida then coalesce(f.es_festivo_canarias, false) end as es_festivo_canarias,
    f.festivo_insular_en,
    case when k.fecha_conocida then coalesce(f.mercados_en_vacaciones_escolares, 0) end
        as mercados_en_vacaciones_escolares
from dias as d
cross join cobertura as c
cross join lateral (select d.fecha between c.desde and c.hasta as fecha_conocida) as k
left join festivos as f on d.fecha = f.fecha
