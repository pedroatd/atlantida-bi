-- Fronteras de las macros de banda: cada caso devuelve la banda esperada y esa banda existe en
-- dim_perfil_huesped.
with casos_edad as (
    select
        anio,
        esperada,
        {{ banda_edad('anio', "date '2025-06-30'") }} as obtenida
    from (
        values
        (null::int, 'desconocida'),
        (1996, 'menos de 30'),
        (1995, '30-44'),
        (1981, '30-44'),
        (1980, '45-59'),
        (1966, '45-59'),
        (1965, '60 o más')
    ) as c (anio, esperada)
),

casos_previas as (
    select
        n,
        esperada,
        {{ banda_estancias_previas('n') }} as obtenida
    from (
        values (0, '0'), (1, '1'), (2, '2-3'), (3, '2-3'), (4, '4 o más'), (25, '4 o más')
    ) as c (n, esperada)
),

perfiles as (
    select
        banda_edad,
        banda_estancias_previas
    from {{ ref('dim_perfil_huesped') }}
),

fallos as (
    select
        'edad' as macro,
        anio::text as entrada,
        obtenida
    from casos_edad
    where
        obtenida is distinct from esperada
        or obtenida not in (select p.banda_edad from perfiles as p)
    union all
    select
        'previas' as macro,
        n::text as entrada,
        obtenida
    from casos_previas
    where
        obtenida is distinct from esperada
        or obtenida not in (select p.banda_estancias_previas from perfiles as p)
)

select * from fallos
