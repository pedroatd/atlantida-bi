{{ config(materialized='table', pre_hook="{{ comprobar_sal() }}") }}
-- Marketing (acción A7). Grupo de cada huésped del golden record en la selección de A7:
-- control (no se marca como VIP) o tratamiento. Una fracción fraccion_control de atlantida.yml,
-- elegida con un hash de la sal secreta del almacén y el golden record: reproducible y auditable
-- en el almacén (la misma sal da el mismo grupo en cada build), pero quien solo conoce el id del
-- golden record no puede saber si es control. Cambiar la sal cambia los grupos, como los
-- seudónimos. Fuente única del grupo: mkt_valor_huesped (reverse ETL) y la medición del impacto
-- lo leen de aquí. Solo ids seudónimos.
-- Sin agregación hash y guardado en orden de huesped_golden_id: int_huespedes_grupos sale de un
-- GROUP BY en el orden de su tabla hash, y una agregación hash que la relee (DISTINCT) o que relee
-- una salida así (la prueba unique) puede degenerar a escala 1: de 0,4 s a más de 10 min
-- (statement_timeout). Ver tests/test_dbt_orden_fisico.py.
with par as (
    select max(valor) filter (where clave = 'accion_A7_fraccion_control')::double precision as fraccion_control
    from {{ ref('def_parametro') }}
),

-- Un golden record por grupo: la fila de la ficha que le da nombre (sin DISTINCT ni GROUP BY).
golden as (
    select huesped_golden_id
    from {{ ref('int_huespedes_grupos') }}
    where huesped_id = huesped_golden_id and huesped_golden_id <> -1
)

select
    g.huesped_golden_id,
    (
        case
            when
                (
                    'x' || lpad(
                        substr(
                            encode(
                                sha256(
                                    convert_to({{ sal_de_sesion() }} || ':A7:' || g.huesped_golden_id::text, 'UTF8')
                                ),
                                'hex'
                            ),
                            1,
                            8
                        ),
                        16,
                        '0'
                    )
                )::bit(64)::bigint % 10000
                < par.fraccion_control * 10000
                then 'control'
            else 'tratamiento'
        end
    )::text as grupo
from golden as g
cross join par
order by g.huesped_golden_id
