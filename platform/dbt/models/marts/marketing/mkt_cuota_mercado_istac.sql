-- Marketing. Cuota de mercado por isla, mes y mercado emisor: viajeros alojados por Atlántida
-- (adultos y niños de las reservas que llegaron: en casa o finalizadas) frente a las llegadas
-- de turistas que publica el ISTAC (FRONTUR-Canarias). Nula si el ISTAC no publica ese mes.
with propios as (
    select
        date_trunc('month', r.fecha_llegada)::date as mes,
        h.isla,
        m.mercado_istac,
        sum(r.adultos + r.ninos) as viajeros
    from {{ ref('fct_reserva') }} as r
    inner join {{ ref('dim_hotel_actual') }} as h on r.hotel_id = h.hotel_id
    inner join {{ ref('dim_mercado') }} as m on r.mercado_sk = m.mercado_sk
    where r.estado in ('en_casa', 'finalizada')
    group by date_trunc('month', r.fecha_llegada)::date, h.isla, m.mercado_istac
)

select
    p.mes,
    p.isla::text as isla,
    p.mercado_istac::text as mercado_istac,
    i.llegadas::double precision as llegadas_istac,
    p.viajeros::double precision as viajeros_atlantida,
    -- reparto descriptivo, no es KPI: cuota de mercado (1.0 evita la división entera: llegadas es bigint)
    (1.0 * p.viajeros / nullif(i.llegadas, 0))::double precision as cuota
from propios as p
left join {{ ref('stg_ext__llegadas_istac') }} as i
    on p.mes = i.mes and p.isla = i.isla and p.mercado_istac = i.mercado_istac
