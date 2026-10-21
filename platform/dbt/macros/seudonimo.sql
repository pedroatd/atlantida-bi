{% macro sal_de_sesion() -%}
    {#- La sal NO se escribe en el SQL: llega en la conexión como parámetro de sesión
        atlantida.sal (PGOPTIONS; ver profiles.yml). Así no aparece en el SQL compilado de target/, en los
        registros de dbt ni en el catálogo de PostgreSQL. -#}
    current_setting('atlantida.sal')
{%- endmacro %}

{% macro seudonimo(expr) -%}
    {#- Seudónimo estable: SHA-256 de la sal y el valor normalizado. Permite unir fichas sin ver
        el dato, pero sigue siendo dato personal (RGPD, art. 4.5): no es anónimo. La sal está en
        platform/.env (make la genera al crearlo) y es secreta: quien la conozca puede
        recuperar por fuerza bruta los valores con pocas posibilidades (fechas, teléfonos).
        Cambiarla cambia todos los seudónimos y crea una versión nueva de cada ficha en
        snp_huespedes y en sat_huesped (de solo inserción): la historia guarda las dos. -#}
    case
        when nullif({{ expr }}, '') is null then null
        else encode(sha256(convert_to({{ sal_de_sesion() }} || ({{ expr }}), 'UTF8')), 'hex')
    end
{%- endmacro %}

{% macro comprobar_sal() -%}
    {#- pre_hook de los modelos que seudonimizan: sin sal, se detiene (dbt lanzado a mano, sin
        atlantida-dbt ni Dagster, que son quienes la ponen en la conexión). -#}
do $$
begin
    if coalesce(current_setting('atlantida.sal', true), '') in ('', 'sin_sal') then
        raise exception 'Falta la sal de los seudónimos: ejecuta dbt con atlantida-dbt (make dbt) o desde Dagster, que la toman de platform/.env.';
    end if;
end
$$
{%- endmacro %}
