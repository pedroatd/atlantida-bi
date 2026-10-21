-- Marketing y direcciones de hotel (acción A7). Valor de cada huésped del golden record: importe
-- en EUR de las reservas no canceladas de las que es titular con llegada en los últimos
-- meses_valor meses hasta la fecha de referencia (la última llegada registrada); su percentil;
-- si es de alto valor (percentil_valor de atlantida.yml); y su grupo (de mkt_grupo_a7: un hash con
-- la sal secreta del almacén, reproducible y auditable). Una fila por ficha del PMS de la
-- que es titular: el reverse ETL marca todas las fichas del golden record. ya_vip indica que el
-- huésped (alguna de sus fichas) ya tiene la marca vip en el PMS, de cualquier origen: el reverse
-- ETL no lo marca de nuevo. Solo ids seudónimos.
with par as (
    select
        max(valor) filter (where clave = 'accion_A7_percentil_valor')::double precision as percentil,
        max(valor) filter (where clave = 'accion_A7_meses_valor')::integer as meses
    from {{ ref('def_parametro') }}
),

referencia as (
    select max(fecha_llegada) as hoy
    from {{ ref('fct_reserva') }}
    where estado in ('en_casa', 'finalizada')
),

valor as (
    select
        r.huesped_golden_id,
        sum(r.importe_total_eur) as valor,
        count(*) as reservas
    from {{ ref('fct_reserva') }} as r
    cross join referencia as x
    cross join par
    where
        not r.es_cancelada
        and r.huesped_golden_id <> -1
        and r.fecha_llegada <= x.hoy
        and r.fecha_llegada > x.hoy - make_interval(months => par.meses)
    group by r.huesped_golden_id
),

rango as (
    select
        huesped_golden_id,
        valor,
        reservas,
        percent_rank() over (order by valor) as percentil_valor
    from valor
),

vip as (
    select distinct g.huesped_golden_id
    from {{ ref('stg_pms__marcas_huesped') }} as m
    inner join {{ ref('int_huespedes_grupos') }} as g on m.huesped_id = g.huesped_id
    where lower(m.marca) = 'vip'
),

fichas as (
    select distinct
        huesped_golden_id,
        huesped_id
    from {{ ref('brg_reserva_huesped') }}
    where es_titular
)

select
    v.huesped_golden_id,
    f.huesped_id,
    v.valor::double precision as valor,
    v.reservas::integer as reservas,
    v.percentil_valor::double precision as percentil_valor,
    (v.percentil_valor >= par.percentil) as es_alto_valor,
    ga.grupo,
    (vip.huesped_golden_id is not null) as ya_vip,
    x.hoy as fecha_referencia
from rango as v
inner join fichas as f on v.huesped_golden_id = f.huesped_golden_id
inner join {{ ref('mkt_grupo_a7') }} as ga on v.huesped_golden_id = ga.huesped_golden_id
left join vip on v.huesped_golden_id = vip.huesped_golden_id
cross join par
cross join referencia as x
