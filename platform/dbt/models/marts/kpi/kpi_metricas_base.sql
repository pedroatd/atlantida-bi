-- Métricas base de atlantida.yml por periodo y ámbito (cada hotel y la cadena). Cada tipo de
-- agregación se respeta: las aditivas se suman, los recuentos de distintos se recalculan sobre el
-- conjunto (no se suman entre hoteles), lo publicado por el compset se pondera por el inventario
-- propio y los días en rojo son un máximo. El pickup se mide al cierre del periodo (hasta); la
-- madurez de las reservas netas, en su corte. Los hoteles se unen con left join: un hecho sin
-- hotel en la dimensión cae en el ámbito '-1' (y en la cadena), nunca se pierde. El ámbito '-1'
-- no es un hotel: los objetivos por hotel deben excluirlo.
--
-- Rejilla densa: cada métrica aditiva o de distintos tiene fila (0 si no hubo hechos) en todos los
-- periodos para cada hotel y la cadena; sin ella, un mes sin detractores o sin cancelaciones daría
-- un KPI nulo en vez de numérico. Solo se densifican las métricas que tienen algún dato en la
-- fuente: una métrica cuya fuente está vacía (dias_aspecto_en_rojo antes del módulo de IA) no
-- aparece, y su KPI queda nulo (sin medida, que no es lo mismo que 0). Lo publicado por el compset
-- y los días en rojo no se densifican: sin informe o sin reseñas clasificadas no hay valor.
-- Excepción en los costes: cost_entry se apunta al cierre contable del mes, así que un
-- hotel-periodo sin ningún apunte de coste (el mes en curso, aún sin cerrar) no tiene medida:
-- coste_total, coste_marketing_atribuido y costes_operativos quedan nulos (no 0), y con ellos el
-- GOPPAR y el CAC. Con algún apunte, la categoría sin apuntes sí vale 0.
--
-- Índices frente al compset (MPI, ARI, RGI): atlantida.yml no fija la cobertura de días. El
-- compset se agrega sobre los días con informe (tiene_dato), ponderado por el inventario STR
-- propio, como hace STR con los datos publicados; el lado propio (noches_vendidas,
-- ingreso_habitaciones, habitaciones_disponibles_str) cubre todos los días del periodo porque
-- esas métricas las comparten otros KPI. Con huecos del proveedor las dos bases difieren en esos
-- días; restringir el lado propio exigiría métricas base propias en la definición.
with periodos as (select * from {{ ref('int_periodos') }}),

hoteles as (
    select
        hotel_id,
        codigo
    from {{ ref('dim_hotel_actual') }}
),

aditivas as (
    select
        p.periodo_id,
        a.metrica,
        case when grouping(h.codigo) = 1 then 'CADENA' else coalesce(h.codigo, '-1') end as ambito,
        sum(a.valor) as valor
    from periodos as p
    inner join {{ ref('int_kpi_aportaciones_diarias') }} as a
        on
            p.desde <= a.fecha
            and p.hasta >= a.fecha
            and (a.valida_hasta is null or p.corte < a.valida_hasta)
    left join hoteles as h on a.hotel_id = h.hotel_id
    group by grouping sets ((p.periodo_id, a.metrica, h.codigo), (p.periodo_id, a.metrica))
),

costes as (
    select
        periodo_id,
        ambito,
        'costes_operativos' as metrica,
        sum(valor) as valor
    from aditivas
    where metrica in ('coste_total', 'comisiones')
    group by periodo_id, ambito
),

distintos as (
    select
        p.periodo_id,
        case when grouping(h.codigo) = 1 then 'CADENA' else coalesce(h.codigo, '-1') end as ambito,
        count(distinct e.huesped_golden_id)::numeric as con_estancia,
        (count(distinct e.huesped_golden_id) filter (where e.repite_24m))::numeric as repetidores
    from periodos as p
    inner join {{ ref('fct_estancia_huesped') }} as e on p.desde <= e.fecha_llegada and p.hasta >= e.fecha_llegada
    left join hoteles as h on e.hotel_id = h.hotel_id
    group by grouping sets ((p.periodo_id, h.codigo), (p.periodo_id))
),

publicados as (
    select
        p.periodo_id,
        case when grouping(h.codigo) = 1 then 'CADENA' else coalesce(h.codigo, '-1') end as ambito,
        sum(c.ocupacion_compset * c.habitaciones_str) filter (where c.tiene_dato)
        / nullif(sum(c.habitaciones_str) filter (where c.tiene_dato), 0) as ocupacion_compset,
        sum(c.revpar_compset * c.habitaciones_str) filter (where c.tiene_dato)
        / nullif(sum(c.ocupacion_compset * c.habitaciones_str) filter (where c.tiene_dato), 0)
            as adr_compset,
        sum(c.revpar_compset * c.habitaciones_str) filter (where c.tiene_dato)
        / nullif(sum(c.habitaciones_str) filter (where c.tiene_dato), 0) as revpar_compset
    from periodos as p
    inner join {{ ref('fct_compset_diario') }} as c on p.desde <= c.fecha and p.hasta >= c.fecha
    left join hoteles as h on c.hotel_id = h.hotel_id
    group by grouping sets ((p.periodo_id, h.codigo), (p.periodo_id))
),

-- Pickup al cierre (hasta): noches futuras (posteriores a hasta) de las reservas creadas o
-- canceladas en los 7 días anteriores. Dos uniones por rango, una por cada fecha.
captadas as (
    select
        p.periodo_id,
        case when grouping(h.codigo) = 1 then 'CADENA' else coalesce(h.codigo, '-1') end as ambito,
        sum(greatest(0, r.fecha_salida - greatest(r.fecha_llegada, p.hasta + 1)))::numeric as valor
    from periodos as p
    inner join {{ ref('fct_reserva') }} as r
        on p.hasta - 7 < r.fecha_reserva and p.hasta >= r.fecha_reserva
    left join hoteles as h on r.hotel_id = h.hotel_id
    group by grouping sets ((p.periodo_id, h.codigo), (p.periodo_id))
),

canceladas as (
    select
        p.periodo_id,
        case when grouping(h.codigo) = 1 then 'CADENA' else coalesce(h.codigo, '-1') end as ambito,
        sum(greatest(0, r.fecha_salida - greatest(r.fecha_llegada, p.hasta + 1)))::numeric as valor
    from periodos as p
    inner join {{ ref('fct_reserva') }} as r
        on p.hasta - 7 < r.fecha_cancelacion and p.hasta >= r.fecha_cancelacion
    left join hoteles as h on r.hotel_id = h.hotel_id
    group by grouping sets ((p.periodo_id, h.codigo), (p.periodo_id))
),

cobertura_aspectos as (
    select
        p.periodo_id,
        case when grouping(h.codigo) = 1 then 'CADENA' else coalesce(h.codigo, '-1') end as ambito,
        count(*) as dias_con_dato
    from periodos as p
    inner join {{ ref('int_aspectos_rojo_diario') }} as d on p.desde <= d.fecha and p.hasta >= d.fecha
    left join hoteles as h on d.hotel_id = h.hotel_id
    group by grouping sets ((p.periodo_id, h.codigo), (p.periodo_id))
),

rachas as (
    select
        p.periodo_id,
        case when grouping(h.codigo) = 1 then 'CADENA' else coalesce(h.codigo, '-1') end as ambito,
        max(least(x.fin, p.hasta) - greatest(x.inicio, p.desde) + 1) as dias
    from periodos as p
    inner join {{ ref('int_rachas_aspecto') }} as x on p.hasta >= x.inicio and p.desde <= x.fin
    left join hoteles as h on x.hotel_id = h.hotel_id
    group by grouping sets ((p.periodo_id, h.codigo), (p.periodo_id))
),

rojo as (
    select
        c.periodo_id,
        c.ambito,
        coalesce(r.dias, 0)::numeric as dias_aspecto_en_rojo
    from cobertura_aspectos as c
    left join rachas as r on c.periodo_id = r.periodo_id and c.ambito = r.ambito
),

-- Hotel-periodos con algún apunte de coste (cierre contable).
con_costes as (
    select distinct
        periodo_id,
        ambito
    from aditivas
    where metrica = 'coste_total'
),

-- Métricas que se densifican (aditivas y de distintos).
sumables as (
    select
        periodo_id,
        ambito,
        metrica,
        valor
    from aditivas
    union all
    select
        periodo_id,
        ambito,
        metrica,
        valor
    from costes
    union all
    select
        periodo_id,
        ambito,
        'huespedes_con_estancia' as metrica,
        con_estancia as valor
    from distintos
    union all
    select
        periodo_id,
        ambito,
        'huespedes_repetidores' as metrica,
        repetidores as valor
    from distintos
    union all
    select
        periodo_id,
        ambito,
        'noches_captadas_ventana' as metrica,
        valor
    from captadas
    union all
    select
        periodo_id,
        ambito,
        'noches_canceladas_ventana' as metrica,
        valor
    from canceladas
),

ambitos as (
    select codigo as ambito from hoteles
    union all
    select 'CADENA' as ambito
),

rejilla as (
    select
        p.periodo_id,
        a.ambito,
        m.metrica
    from periodos as p
    cross join ambitos as a
    cross join (select distinct metrica from sumables) as m
),

densas as (
    select
        g.periodo_id,
        g.ambito,
        g.metrica,
        case
            when
                g.metrica in ('coste_total', 'coste_marketing_atribuido', 'costes_operativos')
                and c.periodo_id is null
                then null
            else coalesce(s.valor, 0)
        end as valor
    from rejilla as g
    left join sumables as s
        on g.periodo_id = s.periodo_id and g.ambito = s.ambito and g.metrica = s.metrica
    left join con_costes as c on g.periodo_id = c.periodo_id and g.ambito = c.ambito
    union all
    -- El ámbito '-1' (hechos sin hotel en la dimensión) solo aparece si tiene datos.
    select
        periodo_id,
        ambito,
        metrica,
        valor
    from sumables
    where ambito = '-1'
),

largas as (
    select
        periodo_id,
        ambito,
        'ocupacion_compset' as metrica,
        ocupacion_compset as valor
    from publicados
    union all
    select
        periodo_id,
        ambito,
        'adr_compset' as metrica,
        adr_compset as valor
    from publicados
    union all
    select
        periodo_id,
        ambito,
        'revpar_compset' as metrica,
        revpar_compset as valor
    from publicados
    union all
    select
        periodo_id,
        ambito,
        'dias_aspecto_en_rojo' as metrica,
        dias_aspecto_en_rojo as valor
    from rojo
)

select
    periodo_id,
    ambito,
    metrica,
    valor
from densas
union all
select
    periodo_id,
    ambito,
    metrica,
    valor
from largas
