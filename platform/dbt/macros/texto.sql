{% macro sin_tildes(expr) -%}
    translate(lower({{ expr }}), 'áàäâãéèëêíìïîóòöôõøúùüûñçå', 'aaaaaeeeeiiiioooooouuuunca')
{%- endmacro %}

{% macro palabras(expr) -%}
    {#- Minúsculas, sin tildes y solo letras y dígitos separados por un espacio. -#}
    trim(regexp_replace({{ sin_tildes(expr) }}, '[^a-z0-9]+', ' ', 'g'))
{%- endmacro %}

{% macro letras_ordenadas(expr) -%}
    {#- Las letras de una palabra en orden alfabético: «garica» y «garcia» dan lo mismo. -#}
    (select string_agg(letra, '' order by letra) from regexp_split_to_table({{ expr }}, '') as letra)
{%- endmacro %}
