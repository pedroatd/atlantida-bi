-- Plantilla de dimensión (L4): una fila por miembro, con su clave sustituta. Cópiala como
-- dim_<entidad>.sql y declárala en modelo.yml (y, si guarda la historia, su bloque scd2).
{{ hueco("elige la clave sustituta, la clave natural y los atributos de la dimensión, y añade el miembro desconocido (-1)") }}
select
    -- COMPLETA: la clave sustituta (entera, única; la usan los hechos) y la clave natural.
    --   Que sea estable al reconstruir: un row_number() cambia cuando llega una versión nueva.
    -- COMPLETA: los atributos descriptivos, de staging (ref) o, si es SCD2, del snapshot.
    -- COMPLETA: en SCD2, el intervalo de validez [desde, hasta) de cada versión y cuál es la vigente.
    --   El snapshot abre la primera versión de cada clave en su última modificación, después de
    --   los hechos más antiguos: haz que la primera versión cubra los hechos más antiguos.
    -- COMPLETA: el miembro desconocido, con clave sustituta -1, para lo que no casa.
    null::bigint as clave_sk
where false
