-- Semáforo diario de cada aspecto de las reseñas por hotel. Parámetros: métrica base
-- dias_aspecto_en_rojo de atlantida.yml (macro generada parametros_metricas; las variables
-- rojo_* solo las usan las pruebas unitarias). Un aspecto está en rojo un día si la media de su
-- polaridad (−1, 0, 1) en las reseñas de los ventana_dias días anteriores está por debajo de
-- umbral con al menos menciones_min menciones; un día con menos menciones conserva el estado del
-- último día con muestra suficiente, como mucho hueco_max_dias días. Solo cuentan las
-- clasificaciones del modelo oficial (el de la ficha oficial vigente de meta.modelo_ia: las
-- filas de modelos oficiales anteriores se conservan en ml como historial) hechas sobre el texto
-- actual de la reseña (huella md5).
{%- set p = parametros_metricas()['dias_aspecto_en_rojo'] %}
{%- set dias_ventana = var('rojo_ventana_dias', p['ventana_dias']) %}
{%- set umbral = var('rojo_umbral', p['umbral']) %}
{%- set minimo = var('rojo_menciones_min', p['menciones_min']) %}
{%- set hueco = var('rojo_hueco_max_dias', p['hueco_max_dias']) %}
with oficial as (
    select modelo
    from {{ source('meta', 'modelo_ia') }}
    where tarea = 'resenas' and oficial
    order by registrado_en desc
    limit 1
),

ultimas as (
    select distinct on (a.review_id, a.aspecto)
        a.review_id,
        a.aspecto,
        a.polaridad,
        a.huella_texto
    from {{ source('ml', 'resena_aspecto') }} as a
    inner join oficial as o on a.modelo = o.modelo
    order by a.review_id asc, a.aspecto asc, a.procesado_en desc
),

menciones as (
    select
        r.hotel_id,
        r.fecha_publicacion as fecha,
        u.aspecto,
        u.polaridad
    from ultimas as u
    inner join {{ ref('stg_pms__resenas') }} as r
        on u.review_id = r.resena_id and u.huella_texto = md5(r.texto)
),

series as (
    select
        hotel_id,
        aspecto,
        min(fecha) as desde,
        max(fecha) as hasta
    from menciones
    group by hotel_id, aspecto
),

dias as (
    select
        s.hotel_id,
        s.aspecto,
        d::date as fecha
    from series as s
    cross join lateral generate_series(s.desde, s.hasta, interval '1 day') as d
),

ventana as (
    select
        d.hotel_id,
        d.aspecto,
        d.fecha,
        count(m.polaridad) as menciones,
        avg(m.polaridad) as sentimiento_medio
    from dias as d
    left join menciones as m
        on
            d.hotel_id = m.hotel_id
            and d.aspecto = m.aspecto
            and d.fecha - {{ dias_ventana }} < m.fecha
            and d.fecha >= m.fecha
    group by d.hotel_id, d.aspecto, d.fecha
),

evaluados as (
    select
        *,
        menciones >= {{ minimo }} as con_muestra,
        case when menciones >= {{ minimo }} then sentimiento_medio < {{ umbral }} end as rojo_con_muestra,
        count(*) filter (where menciones >= {{ minimo }}) over w as grupo,
        max(fecha) filter (where menciones >= {{ minimo }}) over w as ultima_muestra
    from ventana
    window w as (partition by hotel_id, aspecto order by fecha)
)

select
    hotel_id,
    aspecto,
    fecha,
    menciones,
    sentimiento_medio,
    con_muestra,
    coalesce(
        case
            when fecha - ultima_muestra <= {{ hueco }}
                then first_value(rojo_con_muestra) over (partition by hotel_id, aspecto, grupo order by fecha)
        end,
        false
    ) as en_rojo
from evaluados
