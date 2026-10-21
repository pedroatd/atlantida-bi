-- Revenue manager. Tarifas publicadas por la competencia (rate shopper) para cada fecha de
-- estancia, en la consulta hecha 7 días antes: mínima, mediana y máxima del mercado. El contrato
-- del proveedor no asigna competidores a hoteles propios: es una vista del mercado, no del
-- compset de cada hotel. Las filas duplicadas del proveedor se cuentan una vez.
with tarifas as (
    select distinct
        competidor,
        fecha_estancia,
        tarifa
    from {{ ref('stg_ext__tarifas_competencia') }}
    where fecha_consulta = fecha_estancia - 7
)

select
    fecha_estancia,
    count(distinct competidor)::integer as competidores,
    min(tarifa)::double precision as tarifa_min,
    (percentile_cont(0.5) within group (order by tarifa))::double precision as tarifa_mediana,
    max(tarifa)::double precision as tarifa_max
from tarifas
group by fecha_estancia
