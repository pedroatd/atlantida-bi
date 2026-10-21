-- Laboratorio L4, pieza 2: la dimensión del huésped con historia, una SCD de tipo 2 (cap. 8,
-- «Dimensiones lentamente cambiantes»). Una fila por versión del huésped del golden record. Solo
-- el segmento guarda historia (tipo 2); el resto de atributos son los del golden actual (tipo 1)
-- y se repiten en todas sus versiones. Sin datos personales.
-- int_huesped_versiones ya da los intervalos de cada segmento (desde el snapshot snp_huespedes),
-- y int_huesped_golden, los atributos actuales. Las columnas, sus tipos y su orden ya están y no
-- cambian. Mientras tanto el modelo compila y devuelve cero filas. Resuelve cada hueco
-- «-- COMPLETA», borra su marca y quita el «where false».
-- Comprueba con make -C platform l4-comprobar PIEZA=dim_huesped.
with segmentos as (
    select * from {{ ref('int_huesped_versiones') }}
),

golden as (
    select * from {{ ref('int_huesped_golden') }}
)

select
    -- COMPLETA: la clave sustituta de cada versión, estable aunque se reconstruya el modelo.
    -- ¿Qué identifica a una versión y no a otra del mismo huésped? (Mira macros/claves.sql: hay
    -- una macro que da una clave entera, como la columna.)
    cast(null as bigint) as huesped_sk,
    cast(v.huesped_golden_id as bigint) as huesped_golden_id,
    cast(v.segmento as varchar) as segmento,
    -- COMPLETA: los atributos de tipo 1, los del golden actual de cada huésped (int_huesped_golden).
    cast(null as varchar) as pais_codigo,
    cast(null as integer) as anio_nacimiento,
    cast(null as bigint) as num_fichas,
    cast(null as boolean) as tiene_documento,
    cast(null as boolean) as es_contactable,
    -- COMPLETA: la primera versión de cada huésped vale desde 1900-01-01, para que un hecho
    -- anterior a la primera observación encuentre su versión; las demás, desde su inicio.
    cast(v.valido_desde as timestamptz) as valido_desde,
    cast(v.valido_hasta as timestamptz) as valido_hasta,
    -- COMPLETA: ¿qué marca a una versión como vigente? Debe haber una sola por huésped.
    cast(null as boolean) as es_actual
from segmentos as v
where false
-- COMPLETA: añade la fila del miembro desconocido (una fila más al final del modelo), con clave
-- -1 y segmento «desconocido», válida siempre, para que un hecho sin huésped conocido no se
-- pierda (cap. 8, «Miembros especiales»).
