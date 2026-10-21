{% macro fecha_local(expr) -%}
    (({{ expr }}) at time zone 'Atlantic/Canary')::date
{%- endmacro %}

{% macro inicio_dia_local(fecha) -%}
    (({{ fecha }})::timestamp at time zone 'Atlantic/Canary')
{%- endmacro %}
