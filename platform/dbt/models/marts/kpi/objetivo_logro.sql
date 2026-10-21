{{ config(contract={'enforced': true}) }}
-- Índice de logro y semáforo de cada objetivo, con las reglas de atlantida_def.logro (macro
-- agregar_logro): índice = Σ peso · progreso de los principales, redondeado a 12 decimales;
-- verde si llega al umbral y se cumplen todos los guardarraíles; rojo por debajo del umbral
-- ámbar; ámbar en otro caso; logrado si el índice es 1 y se cumplen los guardarraíles.
-- Con algún criterio sin dato, cada resultado solo se da si no depende del dato que falta.
-- datos_completos: todos los criterios tienen dato y sus periodos han madurado.
with par as (
    select
        max(valor) filter (where clave = 'semaforo_verde')::double precision as verde,
        max(valor) filter (where clave = 'semaforo_ambar')::double precision as ambar
    from {{ ref('def_parametro') }}
),

logro as (
    {{ agregar_logro(ref('objetivo_criterio'), '(select verde from par)', '(select ambar from par)') }}
)

select
    l.objetivo_id::text as objetivo_id,
    o.enunciado::text as enunciado,
    l.evaluacion::text as evaluacion,
    l.mes::integer as mes,
    l.ambito::text as ambito,
    l.indice::double precision as indice,
    l.guardarrailes_ok,
    l.datos_completos,
    l.kpis_sin_dato::text as kpis_sin_dato,
    l.semaforo::text as semaforo,
    l.logrado
from logro as l
inner join {{ ref('def_objetivo') }} as o on l.objetivo_id = o.objetivo_id
