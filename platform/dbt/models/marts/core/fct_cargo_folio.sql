{{ config(
    materialized='incremental',
    unique_key='cargo_id',
    incremental_strategy='delete+insert',
    on_schema_change='fail',
    indexes=[{'columns': ['fecha_servicio']}]
) }}
-- Laboratorio L4, pieza 3: el hecho de los cargos de folio (otros ingresos), incremental y con
-- hechos que llegan tarde (cap. 8, «Hechos que llegan tarde»; cap. 13, «Ventanas de reproceso»).
-- Grano: un cargo (cargo_id), sin las repeticiones de una carga duplicada. Un cargo puede anotarse
-- días después de su servicio y llegar en una carga posterior: cuenta en su fecha de servicio,
-- con la versión del hotel vigente ese día. El config de arriba ya es el definitivo: cada
-- ejecución sustituye por cargo_id lo que vuelve a procesar. Las columnas, sus tipos y su orden
-- ya están y no cambian. Mientras tanto el modelo compila y devuelve cero filas. Resuelve cada
-- hueco «-- COMPLETA», borra su marca y quita el «where false».
-- Comprueba con make -C platform l4-comprobar PIEZA=fct_cargo_folio.
with cargos as (
    select * from {{ ref('int_cargos_folio') }}
),

-- Las versiones del hotel (cap. 8, «Dimensiones lentamente cambiantes»).
hoteles as (
    select * from {{ ref('dim_hotel') }}
)

select
    cast(c.cargo_id as bigint) as cargo_id,
    cast(c.reserva_id as bigint) as reserva_id,
    -- COMPLETA: la versión de dim_hotel vigente en la fecha de servicio, no en la de la carga;
    -- sin versión, el miembro desconocido (-1). La macro inicio_dia_local (macros/) da el
    -- instante en que empieza un día en la hora de Canarias.
    cast(null as bigint) as hotel_sk,
    cast(c.hotel_id as bigint) as hotel_id,
    cast(c.fecha_servicio as date) as fecha_servicio,
    cast(c.fecha_registro as date) as fecha_registro,
    cast(c.departamento as varchar) as departamento,
    cast(c.importe as numeric(12, 2)) as importe,
    cast(c.dias_retraso as integer) as dias_retraso,
    cast(c.es_tardio as boolean) as es_tardio,
    cast(c.cargado_en as timestamptz) as cargado_en
from cargos as c
-- COMPLETA: deja fuera las repeticiones de una carga duplicada (int_cargos_folio las marca).
where false
{% if is_incremental() %}
    -- COMPLETA: en una ejecución incremental, ¿desde qué instante de carga vuelves a procesar, y
    -- por qué no solo desde el último cargo que ya está en el modelo? La variable
    -- ventana_reproceso_dias de dbt_project.yml fija la anchura (cap. 13, «Idempotencia» y
    -- «Ventanas de reproceso»).
{% endif %}
