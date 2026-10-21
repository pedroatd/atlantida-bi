-- Revenue manager: cancelación de clientes por cohorte de llegada, canal, tarifa y antelación.
-- Con el canal o el plan de tarifa desconocidos, tipo_canal o es_reembolsable quedan nulos.
{%- set f = formulas_kpi() %}
with reservas as (
    select
        date_trunc('month', r.fecha_llegada)::date as mes_llegada,
        h.codigo as hotel,
        r.tipo_canal,
        -- nulo sin plan de tarifa: desconocido, no «no reembolsable»
        t.es_reembolsable,
        case
            when r.lead_time_dias <= 30 then '0-30'
            when r.lead_time_dias <= 60 then '31-60'
            when r.lead_time_dias <= 180 then '61-180'
            else 'más de 180'
        end as tramo_antelacion,
        r.es_cancelacion_cliente
    from {{ ref('fct_reserva') }} as r
    inner join {{ ref('dim_hotel_actual') }} as h on r.hotel_id = h.hotel_id
    left join {{ ref('dim_tarifa') }} as t on r.tarifa_sk = t.tarifa_sk
),

bases as (
    select
        mes_llegada,
        hotel,
        tipo_canal,
        es_reembolsable,
        tramo_antelacion,
        count(*)::numeric as reservas_llegada,
        (count(*) filter (where es_cancelacion_cliente))::numeric as reservas_canceladas_llegada
    from reservas
    group by mes_llegada, hotel, tipo_canal, es_reembolsable, tramo_antelacion
)

select
    mes_llegada,
    hotel,
    tipo_canal,
    es_reembolsable,
    tramo_antelacion,
    reservas_llegada,
    reservas_canceladas_llegada,
    ({{ f['tasa_cancelacion'] }})::double precision as tasa_cancelacion
from bases
