-- Plantilla de hechos (L4): una fila por suceso del proceso de negocio, con el grano que
-- declaras en modelo.yml. Cópiala como fct_<proceso>.sql.
{{ hueco("declara el grano (una fila por…), une cada dimensión por su clave sustituta (-1 si no casa) y elige las medidas") }}
select
    -- COMPLETA: las columnas del grano: lo que identifica una fila del hecho.
    -- COMPLETA: una clave sustituta por dimensión; en SCD2, la de la versión vigente en la fecha del hecho.
    -- COMPLETA: lo que no casa con su dimensión va al desconocido (-1), nunca a un nulo.
    -- COMPLETA: las medidas (aditivas, semiaditivas…) con su tipo.
    null::bigint as clave_sk
where false
