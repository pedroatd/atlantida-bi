-- Informe diario del compset (tipo STR). El proveedor cambió de formato en algún momento:
-- después publica la ocupación en porcentaje y los importes como texto con coma decimal.
-- Aquí se aceptan los dos formatos y se marca cuál traía cada fila. El formato lo delata la
-- coma de los importes; si la fila no trae importes, se deduce de la escala de la ocupación.
with numeros as (
    select
        hotel_id,
        fecha,
        _loaded_at as cargado_en,
        replace(ocupacion, ',', '.')::numeric as ocupacion_publicada,
        replace(adr, ',', '.')::numeric as adr,
        replace(revpar, ',', '.')::numeric as revpar,
        coalesce(adr like '%,%' or revpar like '%,%', false) as importes_con_coma,
        coalesce(adr is null and revpar is null, false) as sin_importes
    from {{ source('raw_ext', 'compset_diario') }}
),

formato as (
    select
        *,
        case
            when sin_importes then ocupacion_publicada > 1.5
            else importes_con_coma
        end as formato_alternativo
    from numeros
)

select
    hotel_id,
    fecha,
    adr,
    revpar,
    formato_alternativo,
    cargado_en,
    case when formato_alternativo then ocupacion_publicada / 100 else ocupacion_publicada end as ocupacion
from formato
