{% macro clave_sustituta(columnas) -%}
    {#- Clave sustituta entera y estable (60 bits del MD5 de la clave natural): no depende del
        orden de carga, así que reconstruir el modelo no la cambia. -#}
    ('x' || substr(md5(concat_ws('|'
    {%- for c in columnas %}, coalesce(cast({{ c }} as text), '∅'){% endfor -%}
    )), 1, 15))::bit(60)::bigint
{%- endmacro %}

{% macro hash_dv(columnas) -%}
    {#- Clave hash de Data Vault 2.0: MD5 de las claves de negocio normalizadas (recorte y
        mayúsculas, para que «ab1 » y «AB1» sean la misma clave). El delimitador evita que
        ('ab','c') y ('a','bc') den el mismo hash; el marcador de nulo distingue NULL de ''.
        Solo para CLAVES de negocio: los atributos descriptivos usan hashdiff_dv. -#}
    md5(upper(concat_ws('||'
    {%- for c in columnas %}, coalesce(trim(cast({{ c }} as text)), '∅'){% endfor -%}
    )))
{%- endmacro %}

{% macro hashdiff_dv(columnas) -%}
    {#- Huella de los atributos de un satélite. NO normaliza: un cambio de mayúsculas o de
        espacios en «nombre» o «estado» es un cambio real y debe quedar en la historia. El
        delimitador es un carácter de control (chr(31)) que no aparece en los datos. -#}
    md5(concat_ws(chr(31)
    {%- for c in columnas %}, coalesce(cast({{ c }} as text), '∅'){% endfor -%}
    ))
{%- endmacro %}

{% macro hk_fantasma() -%}
    {#- Clave del registro fantasma de Data Vault 2.0: representa «padre desconocido» en un link,
        para no perder la relación (ni la reserva) cuando falta un hotel, canal o huésped. -#}
    '00000000000000000000000000000000'
{%- endmacro %}
