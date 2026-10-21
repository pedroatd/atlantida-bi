-- Revenue manager. Previsión de ocupación oficial del último origen de cada hotel, con el código
-- del hotel. El método oficial es el de la ficha oficial vigente de meta.modelo_ia (parámetro
-- «metodo»); los demás métodos quedan en ml.prevision_ocupacion. Vacía si no hay ficha oficial
-- o hasta que se ejecuta la IA.
with oficial as (
    select parametros ->> 'metodo' as metodo
    from {{ source('meta', 'modelo_ia') }}
    where tarea = 'prevision_ocupacion' and oficial
    order by registrado_en desc
    limit 1
),

ultimo as (
    select
        q.hotel_id,
        max(q.origen) as origen
    from {{ source('ml', 'prevision_ocupacion') }} as q
    inner join oficial as o on q.metodo = o.metodo
    group by q.hotel_id
)

select
    p.fecha,
    coalesce(h.codigo, '-1')::text as hotel,
    p.metodo::text as metodo,
    p.horizonte_dias::integer as horizonte_dias,
    p.ocupacion::double precision as ocupacion,
    p.inferior::double precision as inferior,
    p.superior::double precision as superior,
    p.origen
from {{ source('ml', 'prevision_ocupacion') }} as p
inner join oficial as o on p.metodo = o.metodo
inner join ultimo as u on p.hotel_id = u.hotel_id and p.origen = u.origen
left join {{ ref('dim_hotel_actual') }} as h on p.hotel_id = h.hotel_id
