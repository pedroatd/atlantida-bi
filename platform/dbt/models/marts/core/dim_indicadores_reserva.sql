-- Dimensión «junk»: agrupa indicadores sí/no de la reserva que no merecen una dimensión propia.
with combinaciones as (
    select
        r.v as es_reembolsable,
        d.v as con_deposito,
        c.v as con_campana,
        n.v as con_ninos
    from (values (true), (false)) as r (v)
    cross join (values (true), (false)) as d (v)
    cross join (values (true), (false)) as c (v)
    cross join (values (true), (false)) as n (v)
)

select
    {{ clave_sustituta(['es_reembolsable', 'con_deposito', 'con_campana', 'con_ninos']) }} as indicadores_sk,
    es_reembolsable,
    con_deposito,
    con_campana,
    con_ninos
from combinaciones
union all
-- noqa: disable=AL03
-- Fila del miembro desconocido: las columnas toman el nombre de la primera consulta.
select
    -1,
    null,
    null,
    null,
    null
