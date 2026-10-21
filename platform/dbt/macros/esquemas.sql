{% macro generate_schema_name(custom_schema_name, node) -%}
  {#- Cada capa es un esquema fijo del DWH (contrato C4). En el destino dev, con prefijo dev_:
      dev_staging, dev_marts_kpi… (la migración 06 los crea; solo transformer los ve). -#}
  {%- if target.name not in ('prod', 'dev') -%}
    {{ exceptions.raise_compiler_error("Destino de dbt desconocido: " ~ target.name ~ " (usa prod o dev).") }}
  {%- endif -%}
  {%- set capa = (custom_schema_name or 'staging') | trim -%}
  {{ capa if target.name == 'prod' else 'dev_' ~ capa }}
{%- endmacro %}
