-- Plantilla de staging (L4): una vista por tabla de raw, la única capa que lee raw. Cópiala como
-- stg_<tabla>.sql por cada tabla de tu contrato del L3 y borra esta cuando ya no la necesites.
{{ hueco("lee una tabla de raw con source('raw', '<tabla>') (make fuentes las declara), pon nombres y tipos claros y seudonimiza cada columna de «personales»") }}
select
    -- COMPLETA: la clave natural y los atributos de la tabla, con su tipo (::date, ::numeric…).
    -- COMPLETA: cada columna de «personales», solo seudonimizada: seudonimo('columna') (sin ella).
    -- COMPLETA: la columna de última modificación, si la hay: la necesita el snapshot SCD2.
    -- Ojo: una misma clave puede llegar a raw con tipos distintos (texto desde un CSV, bigint
    -- desde la base de origen): dale aquí un solo tipo (::bigint) para que las uniones casen.
    -- Y los instantes (timestamptz), en UTC sin zona: «actualizado at time zone 'UTC'», el tipo
    -- con el que el snapshot guarda dbt_valid_from (si no, dbt avisa de «DATETIME» y «DATETIMETZ»).
    null::text as columna
where false
