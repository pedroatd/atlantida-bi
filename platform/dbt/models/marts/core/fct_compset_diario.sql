-- Informe del compset por hotel y día, con el inventario propio (base STR) como peso. Los días
-- del periodo publicado sin dato quedan visibles (tiene_dato = false): son huecos del proveedor.
-- El periodo es el horizonte simulado (def_parametro), no el min/max del dato: así una caída del
-- proveedor al principio o al final de la serie aparece como huecos y no como un periodo más corto.
with periodo as (
    select
        max(valor) filter (where clave = 'inicio_historico')::date as desde,
        max(valor) filter (where clave = 'fin_historico')::date as hasta
    from {{ ref('def_parametro') }}
)

select
    i.hotel_id,
    i.fecha,
    c.ocupacion as ocupacion_compset,
    c.adr as adr_compset,
    c.revpar as revpar_compset,
    i.habitaciones as habitaciones_str,
    coalesce(c.ocupacion is not null and c.adr is not null and c.revpar is not null, false) as tiene_dato,
    coalesce(c.formato_alternativo, false) as formato_alternativo
from {{ ref('int_inventario_diario') }} as i
cross join periodo as p
left join {{ ref('stg_ext__compset_diario') }} as c on i.hotel_id = c.hotel_id and i.fecha = c.fecha
where i.fecha between p.desde and p.hasta
