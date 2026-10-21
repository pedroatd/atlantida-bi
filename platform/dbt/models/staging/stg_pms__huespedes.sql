{{ config(materialized='table', pre_hook="{{ comprobar_sal() }}") }}
-- Tabla y no vista: la resolución de duplicados (MDM) lee estos seudónimos muchas veces.
-- Fichas de huésped (guest) SIN datos personales en claro: en su lugar, seudónimos (SHA-256 con
-- sal) de valores normalizados y una clave de nombre, que permiten resolver fichas duplicadas
-- (MDM) sin ver a la persona. Nombre, correo, teléfono, documento y nacimiento solo están en raw.
with base as (
    select
        guest_id,
        {{ palabras('first_name') }} as nombre_n,
        {{ palabras('last_name') }} as apellidos_n,
        lower(trim(email)) as email_n,
        -- últimos 9 dígitos: «+34 612…», «0034612…» y «612…» son el mismo número
        right(regexp_replace(phone, '[^0-9]', '', 'g'), 9) as telefono_n,
        -- documento en mayúsculas y solo letras y dígitos (espacios, guiones y puntos no cuentan;
        -- las letras sí: «AB123456» y «CD123456» son pasaportes distintos)
        nullif(regexp_replace(upper(document_id), '[^A-Z0-9]', '', 'g'), '') as documento_n,
        birth_date,
        country_code,
        segment,
        email is not null as tiene_email,
        phone is not null as tiene_telefono,
        document_id is not null as tiene_documento,
        {{ columnas_tecnicas() }}
    from {{ source('raw_pms', 'guest') }}
),

tokens as (
    select
        *,
        {{ letras_ordenadas("split_part(nombre_n, ' ', 1)") }} as t1,
        {{ letras_ordenadas("split_part(apellidos_n, ' ', 1)") }} as t2
    from base
)

select
    guest_id as huesped_id,
    {{ seudonimo('email_n') }} as seudonimo_email,
    {{ seudonimo('telefono_n') }} as seudonimo_telefono,
    {{ seudonimo('documento_n') }} as seudonimo_documento,
    {{ seudonimo('birth_date::text') }} as seudonimo_nacimiento,
    -- clave de nombre: primer nombre y primer apellido, letras ordenadas y par ordenado
    {{ seudonimo("least(t1, t2) || '|' || greatest(t1, t2)") }} as clave_nombre,
    extract(year from birth_date)::int as anio_nacimiento,
    country_code as pais_codigo,
    {{ traducir('segment', {'leisure_couple': 'pareja_ocio', 'family': 'familia', 'business': 'negocios', 'senior': 'senior', 'group': 'grupo'}) }} as segmento,
    tiene_email,
    tiene_telefono,
    tiene_documento,
    creado_en,
    actualizado_en,
    cargado_en,
    origen_carga
from tokens
