-- Aportación de cada hecho a cada métrica base aditiva, en la fecha que la sitúa (estancia,
-- servicio, coste, creación de la reserva, llegada o publicación) y agregada por hotel y día.
-- Cada hecho se lee una vez y se despliega en filas métrica/valor (cross join lateral values);
-- un valor nulo es una fila que no aporta a esa métrica (p. ej. una reserva no cancelada en
-- ingreso_cancelado).
-- valida_hasta: las métricas «netas» por fecha de creación cuentan la reserva solo si no se
-- había cancelado en la fecha de corte del periodo (madurez, supuesto S14). La fecha de
-- cancelación incluye las reubicaciones (walks): para las reservas netas cuentan como canceladas
-- (S15), aunque no son cancelaciones del cliente en las métricas por cohorte de llegada.
with ocupacion as (
    select
        o.hotel_id,
        o.fecha,
        v.metrica,
        v.valor,
        null::date as valida_hasta
    from {{ ref('fct_ocupacion_diaria') }} as o
    cross join lateral (
        values
        ('habitaciones_disponibles', o.disponibles::numeric),
        ('habitaciones_disponibles_str', o.habitaciones::numeric),
        ('noches_vendidas', o.noches_vendidas::numeric),
        ('noches_vendidas_directo', o.noches_vendidas_directo::numeric),
        ('ingreso_habitaciones', o.ingreso_habitaciones::numeric)
    ) as v (metrica, valor)
),

comisiones as (
    select
        hotel_id,
        fecha_estancia as fecha,
        'comisiones' as metrica,
        comision::numeric as valor,
        null::date as valida_hasta
    from {{ ref('fct_noche_estancia') }}
),

otros_ingresos as (
    select
        hotel_id,
        fecha_servicio as fecha,
        'ingreso_otros' as metrica,
        importe::numeric as valor,
        null::date as valida_hasta
    from {{ ref('fct_cargo_folio') }}
),

costes as (
    select
        k.hotel_id,
        k.fecha_coste as fecha,
        v.metrica,
        v.valor,
        null::date as valida_hasta
    from {{ ref('fct_coste') }} as k
    cross join lateral (
        values
        ('coste_total', k.importe::numeric),
        ('coste_marketing_atribuido', case when k.categoria = 'marketing' then k.importe::numeric end)
    ) as v (metrica, valor)
),

-- Por fecha de creación de la reserva (las netas, con su estado al corte).
reservas_creadas as (
    select
        r.hotel_id,
        r.fecha_reserva as fecha,
        v.metrica,
        v.valor,
        v.valida_hasta
    from {{ ref('fct_reserva') }} as r
    cross join lateral (
        values
        ('reservas_creadas', 1::numeric, null::date),
        ('lead_time', r.lead_time_dias::numeric, null::date),
        ('reservas_netas', 1::numeric, r.fecha_cancelacion),
        ('noches_por_reserva', r.noches::numeric, r.fecha_cancelacion),
        ('noches_reservadas_directo', case when r.es_directo then r.noches::numeric end, r.fecha_cancelacion)
    ) as v (metrica, valor, valida_hasta)
),

-- Por cohorte de llegada: cancelación = cancelación del cliente (sin reubicaciones).
reservas_llegada as (
    select
        r.hotel_id,
        r.fecha_llegada as fecha,
        v.metrica,
        v.valor,
        null::date as valida_hasta
    from {{ ref('fct_reserva') }} as r
    cross join lateral (
        values
        ('reservas_llegada', 1::numeric),
        ('reservas_canceladas_llegada', case when r.es_cancelacion_cliente then 1::numeric end),
        ('reservas_llegada_ota', case when r.es_ota then 1::numeric end),
        ('reservas_canceladas_llegada_ota', case when r.es_ota and r.es_cancelacion_cliente then 1::numeric end),
        ('ingreso_reservado', r.importe_total_eur),
        ('ingreso_cancelado', case when r.es_cancelacion_cliente then r.importe_total_eur end),
        ('penalizaciones_retenidas', case when r.es_cancelacion_cliente then r.importe_penalizacion_cliente end),
        ('ingreso_reventa', case when r.es_cancelacion_cliente then r.ingreso_reventa_eur end)
    ) as v (metrica, valor)
),

resenas as (
    select
        s.hotel_id,
        s.fecha_publicacion as fecha,
        v.metrica,
        v.valor,
        null::date as valida_hasta
    from {{ ref('fct_resena') }} as s
    cross join lateral (
        values
        ('promotores', case when s.es_promotor then 1::numeric end),
        ('detractores', case when s.es_detractor then 1::numeric end),
        ('respuestas_recomendacion', case when s.tiene_recomendacion then 1::numeric end)
    ) as v (metrica, valor)
),

aportaciones as (
    select * from ocupacion
    union all
    select * from comisiones
    union all
    select * from otros_ingresos
    union all
    select * from costes
    union all
    select * from reservas_creadas
    union all
    select * from reservas_llegada
    union all
    select * from resenas
)

select
    hotel_id,
    fecha,
    metrica,
    valida_hasta,
    sum(valor) as valor
from aportaciones
where valor is not null
group by hotel_id, fecha, metrica, valida_hasta
