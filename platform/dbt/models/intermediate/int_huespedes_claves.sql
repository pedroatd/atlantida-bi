-- Claves de coincidencia de cada ficha (todas seudonimizadas). Dos fichas son la misma persona
-- si comparten documento; o correo o teléfono junto con el nombre o la fecha de nacimiento; o
-- nombre y fecha de nacimiento. Una clave que comparten demasiadas fichas (un correo de agencia,
-- un teléfono de recepción) no sirve para unir: se descarta (bloqueo por frecuencia).
with h as (
    select * from {{ ref('stg_pms__huespedes') }}
),

claves as (
    select
        huesped_id,
        'documento' as regla,
        seudonimo_documento as valor
    from h
    where seudonimo_documento is not null
    union all
    select
        huesped_id,
        'email_nombre' as regla,
        seudonimo_email || ':' || clave_nombre as valor
    from h
    where seudonimo_email is not null and clave_nombre is not null
    union all
    select
        huesped_id,
        'email_nacimiento' as regla,
        seudonimo_email || ':' || seudonimo_nacimiento as valor
    from h
    where seudonimo_email is not null and seudonimo_nacimiento is not null
    union all
    select
        huesped_id,
        'telefono_nombre' as regla,
        seudonimo_telefono || ':' || clave_nombre as valor
    from h
    where seudonimo_telefono is not null and clave_nombre is not null
    union all
    select
        huesped_id,
        'telefono_nacimiento' as regla,
        seudonimo_telefono || ':' || seudonimo_nacimiento as valor
    from h
    where seudonimo_telefono is not null and seudonimo_nacimiento is not null
    union all
    select
        huesped_id,
        'nombre_nacimiento' as regla,
        clave_nombre || ':' || seudonimo_nacimiento as valor
    from h
    where clave_nombre is not null and seudonimo_nacimiento is not null
),

frecuentes as (
    select
        regla,
        valor
    from claves
    group by regla, valor
    having count(*) > {{ var('mdm_max_fichas_por_clave') }}
)

select
    c.huesped_id,
    c.regla,
    c.valor
from claves as c
left join frecuentes as f on c.regla = f.regla and c.valor = f.valor
where f.valor is null
