{% macro traducir(columna, valores) -%}
    case {{ columna }}
    {%- for origen, destino in valores.items() %}
        when '{{ origen }}' then '{{ destino }}'
    {%- endfor %}
        else {{ columna }}
    end
{%- endmacro %}
