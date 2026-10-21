-- Meteorología diaria de la estación del aeropuerto de cada isla (AEMET u Open-Meteo).
select
    fecha,
    isla,
    estacion,
    precipitacion as precipitacion_mm,
    temperatura_maxima as temperatura_maxima_c,
    _loaded_at as cargado_en,
    case when estacion like 'OM-%' then 'Open-Meteo' else 'AEMET' end as fuente_dato
from {{ source('raw_ext', 'aemet_diario') }}
