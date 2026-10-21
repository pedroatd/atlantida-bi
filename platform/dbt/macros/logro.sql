{#- Reglas del índice de logro, idénticas a atlantida_def.logro (ver su documentación): magnitud
    comparada, cumplimiento con tolerancia a favor, progreso de un criterio principal y, por
    objetivo, índice, guardarraíles, semáforo y logrado.

    Sin dato: atlantida_def solo evalúa un objetivo con el valor (base, actual) de todos sus KPI y
    no define la variación relativa sobre una base 0. (Ojo: greatest y least de PostgreSQL ignoran
    los nulos; por eso el progreso comprueba antes que la magnitud no sea nula.) En SQL, un criterio así tiene magnitud,
    cumplimiento y progreso nulos, y cada resultado del objetivo (índice, guardarraíles, semáforo,
    logrado) se da solo si es el mismo para cualquier valor que pudiera tomar el dato que falta;
    si no, queda nulo (el semáforo, «sin_datos»). Es la regla de atlantida_def.evaluar_objetivo_parcial. -#}

{#- Un criterio tiene dato si tiene los dos valores (base, actual), como exige evaluar_objetivo,
    también en un umbral (que solo compara el actual, pero necesita la base para el progreso). -#}
{% macro magnitud_criterio(tipo, base, actual) -%}
    case
        when {{ base }} is null or {{ actual }} is null then null
        when {{ tipo }} = 'variacion_relativa'
            then case when {{ base }} = 0 then null else {{ actual }} / {{ base }} - 1 end
        when {{ tipo }} = 'variacion_absoluta' then {{ actual }} - {{ base }}
        else {{ actual }}
    end
{%- endmacro %}

{% macro cumple_criterio(sentido, magnitud, meta, tolerancia) -%}
    case
        when {{ magnitud }} is null then null
        when {{ sentido }} = 'al_menos' then {{ magnitud }} >= {{ meta }} - {{ tolerancia }}
        else {{ magnitud }} <= {{ meta }} + {{ tolerancia }}
    end
{%- endmacro %}

{% macro progreso_criterio(papel, tipo, sentido, meta, base, actual, magnitud, cumple) -%}
    case
        when {{ papel }} <> 'principal' or {{ magnitud }} is null then null
        when {{ cumple }} then 1.0
        when {{ tipo }} = 'umbral'
            then
                case
                    when
                        ({{ sentido }} = 'al_menos' and {{ meta }} <= {{ base }})
                        or ({{ sentido }} = 'como_maximo' and {{ meta }} >= {{ base }})
                        then 0.0
                    else greatest(0.0, least(1.0, ({{ actual }} - {{ base }}) / ({{ meta }} - {{ base }})))
                end
        when
            {{ meta }} = 0 or ({{ sentido }} = 'al_menos' and {{ meta }} < 0)
            or ({{ sentido }} = 'como_maximo' and {{ meta }} > 0)
            then 0.0
        else greatest(0.0, least(1.0, {{ magnitud }} / {{ meta }}))
    end
{%- endmacro %}

{#- Índice redondeado a 12 decimales como round(x, 12) en Python, desde el texto más corto que
    representa el double (el cast directo a numeric solo guarda 15 cifras). Python redondea el valor
    binario exacto a la mitad par: en un empate en la decimotercera cifra pueden diferir en 1e-12,
    por eso la comprobación cruzada compara el índice con tolerancia. La suma sigue el orden de los
    criterios, como evaluar_objetivo. -#}
{% macro _indice_logro(progreso) -%}
    round(
        (sum(peso * {{ progreso }} order by orden) filter (where papel = 'principal'))::text::numeric, 12
    )::double precision
{%- endmacro %}

{% macro _semaforo_logro(indice, guardarrailes_ok, verde, ambar) -%}
    case
        when {{ indice }} >= {{ verde }} and {{ guardarrailes_ok }} then 'verde'
        when {{ indice }} < {{ ambar }} then 'rojo'
        else 'ambar'
    end
{%- endmacro %}

{#- Resultado de cada objetivo (objetivo_id, evaluacion, mes, ambito) a partir de sus criterios
    (columnas de objetivo_criterio). Para lo que falta se toman los dos extremos: el peor
    (progreso 0, guardarraíl incumplido) y el mejor (progreso 1, guardarraíl cumplido); como el
    semáforo y logrado crecen con el índice y con los guardarraíles, si los dos extremos coinciden
    el resultado no depende del dato que falta. -#}
{% macro agregar_logro(criterios, verde, ambar) -%}
    select
        objetivo_id,
        evaluacion,
        mes,
        ambito,
        case when principales_completos then indice_peor end as indice,
        guardarrailes_ok,
        datos_completos,
        kpis_sin_dato,
        case
            when
                {{ _semaforo_logro('indice_peor', 'coalesce(guardarrailes_ok, false)', verde, ambar) }}
                = {{ _semaforo_logro('indice_mejor', 'coalesce(guardarrailes_ok, true)', verde, ambar) }}
                then {{ _semaforo_logro('indice_peor', 'coalesce(guardarrailes_ok, false)', verde, ambar) }}
            else 'sin_datos'
        end as semaforo,
        case
            when (indice_peor >= 1.0 and coalesce(guardarrailes_ok, false))
                = (indice_mejor >= 1.0 and coalesce(guardarrailes_ok, true))
                then indice_peor >= 1.0 and coalesce(guardarrailes_ok, false)
        end as logrado
    from (
        select
            objetivo_id,
            evaluacion,
            mes,
            ambito,
            {{ _indice_logro('coalesce(progreso, 0.0)') }} as indice_peor,
            {{ _indice_logro('coalesce(progreso, 1.0)') }} as indice_mejor,
            coalesce(bool_and(progreso is not null) filter (where papel = 'principal'), false)
                as principales_completos,
            case
                when bool_or(not cumple) filter (where papel = 'guardarrail') then false
                when bool_or(cumple is null) filter (where papel = 'guardarrail') then null
                else true
            end as guardarrailes_ok,
            bool_and(magnitud is not null and completo) as datos_completos,
            string_agg(kpi, ', ' order by orden) filter (where magnitud is null) as kpis_sin_dato
        from {{ criterios }}
        group by objetivo_id, evaluacion, mes, ambito
    ) as agregado
{%- endmacro %}
