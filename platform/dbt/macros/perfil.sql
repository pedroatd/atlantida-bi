{% macro banda_edad(anio_nacimiento, fecha) -%}
    case
        when {{ anio_nacimiento }} is null then 'desconocida'
        when extract(year from {{ fecha }}) - {{ anio_nacimiento }} < 30 then 'menos de 30'
        when extract(year from {{ fecha }}) - {{ anio_nacimiento }} < 45 then '30-44'
        when extract(year from {{ fecha }}) - {{ anio_nacimiento }} < 60 then '45-59'
        else '60 o más'
    end
{%- endmacro %}

{% macro banda_estancias_previas(n) -%}
    case when {{ n }} = 0 then '0' when {{ n }} = 1 then '1' when {{ n }} <= 3 then '2-3' else '4 o más' end
{%- endmacro %}
