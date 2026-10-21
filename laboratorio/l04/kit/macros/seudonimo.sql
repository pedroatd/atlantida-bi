{% macro seudonimo(expr) -%}
    {#- Seudónimo estable de un dato personal: SHA-256 de la sal y el valor (como texto). Permite
        unir y contar sin ver el dato, pero sigue siendo dato personal (RGPD, art. 4.5): no es
        anónimo. La sal NO se escribe en el SQL: llega en la conexión como parámetro de sesión
        proyecto.sal (PGOPTIONS, que pone el Makefile desde .env; make sal la genera). Así no
        aparece en el SQL compilado de target/, en logs/ ni en el catálogo de PostgreSQL.
        Quien conozca la sal puede recuperar por fuerza bruta los valores con pocas
        posibilidades (fechas, códigos postales): guárdala como una contraseña. -#}
    case
        when nullif(({{ expr }})::text, '') is null then null
        else encode(sha256(convert_to(current_setting('proyecto.sal') || ({{ expr }})::text, 'UTF8')), 'hex')
    end
{%- endmacro %}

{% macro comprobar_sal() -%}
    {#- pre-hook de staging: sin sal en la conexión (dbt lanzado sin make), se detiene. -#}
do $$
begin
    if coalesce(current_setting('proyecto.sal', true), '') = '' then
        raise exception 'Falta la sal de los seudónimos: ejecuta dbt con make (make dbt, make snapshot), que la toma de .env (make sal la genera).';
    end if;
end
$$
{%- endmacro %}
