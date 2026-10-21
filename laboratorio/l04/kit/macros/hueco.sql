{% macro hueco(pista) -%}
    {#- Marca una plantilla sin completar: al construirla, dbt se detiene y dice qué falta. Quita
        la llamada cuando la completes (o borra la plantilla si no la usas). -#}
    {%- if execute -%}
        {{ exceptions.raise_compiler_error("completa " ~ model.original_file_path ~ ": " ~ pista ~ " (o bórrala si no la usas)") }}
    {%- endif -%}
{%- endmacro %}
