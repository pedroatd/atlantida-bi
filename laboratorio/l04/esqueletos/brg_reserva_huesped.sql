-- Laboratorio L4, pieza 1: la tabla puente entre reservas y huéspedes (cap. 8, «Tablas puente»).
-- Grano: una fila por cada fila de stg_pms__reservas_huespedes (el titular y sus acompañantes);
-- ninguna fila del origen se pierde. Las columnas, sus tipos y su orden ya están y no cambian: lo
-- que las lee aguas abajo (y las pruebas) cuenta con ellos. Mientras tanto el modelo compila y
-- devuelve cero filas. Resuelve cada hueco «-- COMPLETA», borra su marca y quita el «where false».
-- Comprueba con make -C platform l4-comprobar PIEZA=brg_reserva_huesped.
with reservas_huespedes as (
    select * from {{ ref('stg_pms__reservas_huespedes') }}
),

reservas as (
    select * from {{ ref('stg_pms__reservas') }}
),

-- La ficha del PMS → su huésped en el golden record (resuelto en int_huespedes_grupos).
fichas as (
    select * from {{ ref('int_huespedes_grupos') }}
),

-- Las versiones de la dimensión del huésped (cap. 8, «Dimensiones lentamente cambiantes»).
huespedes as (
    select * from {{ ref('dim_huesped') }}
)

select
    cast(rh.reserva_id as bigint) as reserva_id,
    cast(rh.huesped_id as bigint) as huesped_id,
    -- COMPLETA: el huésped del golden record de cada ficha; una ficha sin él va al miembro
    -- desconocido, la clave -1 (cap. 8, «Miembros especiales»).
    cast(null as bigint) as huesped_golden_id,
    -- COMPLETA: la versión de dim_huesped vigente cuando se hizo la reserva (sus intervalos son
    -- semiabiertos: desde incluido, hasta excluido); sin versión, el miembro desconocido.
    cast(null as bigint) as huesped_sk,
    cast(rh.es_titular as boolean) as es_titular,
    -- COMPLETA: la parte de la reserva que corresponde a cada huésped, para que una medida de la
    -- reserva sumada por huésped no se cuente varias veces: el factor de ponderación suma 1 en
    -- cada reserva (cap. 8, «Tablas puente»).
    cast(null as numeric) as factor_ponderacion
from reservas_huespedes as rh
-- COMPLETA: une las reservas (su instante de reserva), las fichas y las versiones del huésped sin
-- perder ninguna fila del origen.
where false
