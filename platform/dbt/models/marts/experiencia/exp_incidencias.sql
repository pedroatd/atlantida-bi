-- Direcciones de hotel. Incidencias por hotel y día: habitaciones fuera de servicio (room_block),
-- aspectos de las reseñas en rojo (semáforo) y días anómalos de los KPI diarios (módulo de IA).
-- Una fila por día, hotel, tipo y detalle; cantidad = habitaciones, aspectos o métodos.
with bloqueos as (
    select
        d.dia::date as fecha,
        coalesce(h.codigo, '-1') as hotel,
        'fuera_de_servicio' as tipo,
        coalesce(b.motivo, 'sin motivo') as detalle,
        count(*) as cantidad
    from {{ ref('stg_pms__bloqueos') }} as b
    inner join {{ ref('dim_habitacion') }} as hab on b.habitacion_id = hab.habitacion_id
    left join {{ ref('dim_hotel_actual') }} as h on hab.hotel_id = h.hotel_id
    cross join lateral generate_series(b.fecha_inicio, b.fecha_fin, interval '1 day') as d (dia)
    group by d.dia::date, coalesce(h.codigo, '-1'), coalesce(b.motivo, 'sin motivo')
),

rojos as (
    select
        fecha,
        hotel,
        'aspecto_en_rojo' as tipo,
        aspecto as detalle,
        count(*) as cantidad
    from {{ ref('exp_aspectos_diario') }}
    where en_rojo
    group by fecha, hotel, aspecto
),

anomalias as (
    select
        fecha,
        ambito as hotel,
        'anomalia_kpi' as tipo,
        kpi as detalle,
        count(*) as cantidad
    from {{ source('ml', 'anomalia_kpi') }}
    where es_anomalia and ambito <> 'CADENA'
    group by fecha, ambito, kpi
)

select
    fecha,
    hotel::text as hotel,
    tipo::text as tipo,
    detalle::text as detalle,
    cantidad::integer as cantidad
from bloqueos
union all
select
    fecha,
    hotel::text,
    tipo::text,
    detalle::text,
    cantidad::integer
from rojos
union all
select
    fecha,
    hotel::text,
    tipo::text,
    detalle::text,
    cantidad::integer
from anomalias
