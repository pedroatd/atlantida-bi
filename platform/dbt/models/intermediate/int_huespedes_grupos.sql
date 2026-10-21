-- Grupos de fichas de la misma persona: cierre transitivo de las coincidencias (si A coincide
-- con B y B con C, las tres son la misma persona). El golden record se identifica con la ficha
-- más antigua del grupo (el menor huesped_id). Pertenencia tipo 1: se recalcula en cada build.
with recursive enlaces as (
    select
        huesped_a as desde,
        huesped_b as hasta
    from {{ ref('int_huespedes_aristas') }}
    union all
    select
        huesped_b as desde,
        huesped_a as hasta
    from {{ ref('int_huespedes_aristas') }}
),

alcance (huesped_id, alcanzado) as (
    select
        huesped_id,
        huesped_id as alcanzado
    from {{ ref('stg_pms__huespedes') }}
    union
    select
        a.huesped_id,
        e.hasta as alcanzado
    from alcance as a
    inner join enlaces as e on a.alcanzado = e.desde
)

select
    huesped_id,
    min(alcanzado) as huesped_golden_id,
    count(*) as fichas_del_grupo
from alcance
group by huesped_id
