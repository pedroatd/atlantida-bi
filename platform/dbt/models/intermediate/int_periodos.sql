-- Periodos de cálculo de los KPI: años y meses con datos, y los acumulados del año (YTD) del
-- periodo base y del evaluado para el seguimiento mensual. corte = fin del periodo + madurez.
-- completo: el corte ya ha pasado según los datos (reloj = última fecha de reserva registrada,
-- sin pasar de fin_historico); hasta entonces las reservas netas del periodo no están maduras.
-- Los periodos se limitan al horizonte simulado (def_parametro): la historia previa de huéspedes
-- solo sirve para la repetición y no abre periodos.
with par as (
    select
        max(valor) filter (where clave = 'periodo_base')::int as periodo_base,
        max(valor) filter (where clave = 'periodo_evaluado')::int as periodo_evaluado,
        max(valor) filter (where clave = 'madurez_dias')::int as madurez_dias,
        max(valor) filter (where clave = 'inicio_historico')::date as inicio_historico,
        max(valor) filter (where clave = 'fin_historico')::date as fin_historico
    from {{ ref('def_parametro') }}
),

limites as (
    select
        greatest(min(o.fecha), max(par.inicio_historico)) as primero,
        least(max(o.fecha), max(par.fin_historico)) as ultimo
    from {{ ref('fct_ocupacion_diaria') }} as o
    cross join par
),

reloj as (
    select least(max(r.fecha_reserva), max(par.fin_historico)) as hoy
    from {{ ref('fct_reserva') }} as r
    cross join par
),

anios_ytd as (
    select periodo_base as anio from par
    union
    select periodo_evaluado as anio from par
),

periodos as (
    select
        a::text as periodo_id,
        'anio' as tipo_periodo,
        a as anio,
        null::int as mes,
        make_date(a, 1, 1) as desde,
        make_date(a, 12, 31) as hasta
    from limites
    cross join generate_series(extract(year from primero)::int, extract(year from ultimo)::int) as a
    union all
    select
        to_char(m, 'YYYY-MM') as periodo_id,
        'mes' as tipo_periodo,
        extract(year from m)::int as anio,
        extract(month from m)::int as mes,
        m::date as desde,
        (m + interval '1 month - 1 day')::date as hasta
    from limites
    cross join generate_series(date_trunc('month', primero), ultimo, interval '1 month') as m
    union all
    select
        a.anio || '-YTD-' || lpad(m::text, 2, '0') as periodo_id,
        'ytd' as tipo_periodo,
        a.anio,
        m as mes,
        make_date(a.anio, 1, 1) as desde,
        (make_date(a.anio, m, 1) + interval '1 month - 1 day')::date as hasta
    from anios_ytd as a
    cross join generate_series(1, 12) as m
)

select
    p.*,
    p.hasta + par.madurez_dias as corte,
    p.hasta + par.madurez_dias <= k.hoy as completo
from periodos as p
cross join par
cross join reloj as k
