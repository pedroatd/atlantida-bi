{{ config(materialized='view') }}
-- Versión vigente de cada hotel (para cruzar por código sin pensar en versiones).
select
    hotel_sk,
    hotel_id,
    codigo,
    nombre,
    isla,
    municipio,
    tipo_hotel,
    estrellas
from {{ ref('dim_hotel') }}
where es_actual and hotel_sk <> -1
