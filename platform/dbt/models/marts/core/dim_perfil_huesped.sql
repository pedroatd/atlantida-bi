-- Mini-dimensión de perfil: atributos del huésped que cambian a menudo (banda de edad, si es del
-- programa de fidelización, estancias previas). Se separan de dim_huesped para no multiplicar
-- sus versiones: cada hecho apunta al perfil que tenía el huésped en ese momento. El segmento
-- también está aquí (además de en dim_huesped) para poder filtrar perfiles completos sin cruzar
-- dimensiones.
with segmentos as (
    select unnest(array['pareja_ocio', 'familia', 'negocios', 'senior', 'grupo', 'desconocido']) as segmento
),

edades as (
    select unnest(array['menos de 30', '30-44', '45-59', '60 o más', 'desconocida']) as banda_edad
),

miembros as (
    select unnest(array[true, false]) as es_miembro_programa
),

previas as (
    select unnest(array['0', '1', '2-3', '4 o más']) as banda_estancias_previas
)

select
    {{ clave_sustituta(['s.segmento', 'e.banda_edad', 'm.es_miembro_programa', 'p.banda_estancias_previas']) }}
        as perfil_sk,
    s.segmento,
    e.banda_edad,
    m.es_miembro_programa,
    p.banda_estancias_previas
from segmentos as s
cross join edades as e
cross join miembros as m
cross join previas as p
union all
-- noqa: disable=AL03
-- Fila del miembro desconocido: las columnas toman el nombre de la primera consulta.
select
    -1,
    'desconocido',
    'desconocida',
    false,
    'desconocida'
