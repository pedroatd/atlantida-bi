-- Costes operativos, una fila por apunte de coste (base del GOP). Versión del hotel vigente al
-- empezar el día (hora canaria).
select
    k.coste_id,
    coalesce(h.hotel_sk, -1) as hotel_sk,
    k.hotel_id,
    k.fecha_coste,
    k.categoria,
    k.importe
from {{ ref('stg_pms__costes') }} as k
left join {{ ref('dim_hotel') }} as h
    on
        k.hotel_id = h.hotel_id
        and {{ inicio_dia_local('k.fecha_coste') }} >= h.valido_desde
        and {{ inicio_dia_local('k.fecha_coste') }} < h.valido_hasta
