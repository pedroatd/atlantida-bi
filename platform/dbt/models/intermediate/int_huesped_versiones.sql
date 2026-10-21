-- Historia del segmento del golden record a partir de las versiones de sus fichas: en cada
-- instante manda la ficha actualizada más recientemente del grupo (la misma regla de
-- supervivencia que int_huesped_golden); los tramos consecutivos con el mismo segmento se funden
-- (técnica de «islas y huecos»). Intervalos semiabiertos [valido_desde, valido_hasta).
with grupos as (
    select
        huesped_id,
        huesped_golden_id
    from {{ ref('int_huespedes_grupos') }}
),

versiones as (
    select
        g.huesped_golden_id,
        s.huesped_id,
        s.segmento,
        s.actualizado_en,
        s.dbt_valid_from as desde,
        s.dbt_valid_to as hasta
    from {{ ref('snp_huespedes') }} as s
    inner join grupos as g on s.huesped_id = g.huesped_id
),

puntos as (
    select distinct
        huesped_golden_id,
        desde as inicio
    from versiones
),

tramos as (
    select
        huesped_golden_id,
        inicio,
        lead(inicio, 1, '9999-12-31 00:00:00+00'::timestamptz) over w as fin
    from puntos
    window w as (partition by huesped_golden_id order by inicio)
),

estado as (
    select
        t.huesped_golden_id,
        t.inicio,
        t.fin,
        (array_agg(v.segmento order by v.actualizado_en desc, v.huesped_id desc))[1] as segmento
    from tramos as t
    inner join versiones as v
        on
            t.huesped_golden_id = v.huesped_golden_id
            and t.inicio >= v.desde
            and t.inicio < v.hasta
    group by t.huesped_golden_id, t.inicio, t.fin
),

anteriores as (
    select
        *,
        lag(segmento) over (partition by huesped_golden_id order by inicio) as segmento_anterior
    from estado
),

cambios as (
    select
        *,
        (segmento is distinct from segmento_anterior)::int as cambio
    from anteriores
),

islas as (
    select
        *,
        sum(cambio) over (partition by huesped_golden_id order by inicio) as isla
    from cambios
)

select
    huesped_golden_id,
    segmento,
    min(inicio) as valido_desde,
    max(fin) as valido_hasta
from islas
group by huesped_golden_id, segmento, isla
