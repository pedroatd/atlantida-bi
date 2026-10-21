-- Tiempo de cada isla y día (estación del aeropuerto): dimensión para cruzar estancias y reservas
-- con la meteorología.
select
    {{ clave_sustituta(['isla', 'fecha']) }} as meteo_sk,
    isla,
    fecha,
    precipitacion_mm,
    temperatura_maxima_c,
    precipitacion_mm >= 0.1 as dia_lluvioso,  -- criterio de AEMET; nulo si no hay dato
    case
        when temperatura_maxima_c is null then 'sin dato'
        when temperatura_maxima_c < 20 then 'menos de 20 °C'
        when temperatura_maxima_c < 25 then '20-25 °C'
        when temperatura_maxima_c < 30 then '25-30 °C'
        else '30 °C o más'
    end as banda_temperatura,
    fuente_dato
from {{ ref('stg_ext__meteo_diaria') }}
union all
-- noqa: disable=AL03
-- Fila del miembro desconocido: las columnas toman el nombre de la primera consulta.
select
    -1,
    'Desconocida',
    null,
    null,
    null,
    null,
    'sin dato',
    'N/D'
