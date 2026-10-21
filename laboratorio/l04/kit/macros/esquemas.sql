{% macro generate_schema_name(custom_schema_name, node) -%}
    {#- Cada capa es un esquema fijo de tu base: staging, snapshots y marts (sin el prefijo que
        dbt añade por omisión). -#}
    {{ (custom_schema_name or target.schema) | trim }}
{%- endmacro %}
