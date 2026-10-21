{% macro motor_el() %}{{ return(var('motor_el', env_var('MOTOR_EL', 'dlt'))) }}{% endmacro %}

{% macro columnas_tecnicas() -%}
    {#- Columnas de control comunes de staging: cuándo se creó y cambió la fila en el PMS, cuándo
        se cargó y por qué camino (pms, api o airbyte). -#}
    created_at as creado_en,
    updated_at as actualizado_en,
    {{ '_airbyte_extracted_at' if motor_el() == 'airbyte' else '_loaded_at' }} as cargado_en,
    {{ "'airbyte'" if motor_el() == 'airbyte' else '_origen' }} as origen_carga
{%- endmacro %}
