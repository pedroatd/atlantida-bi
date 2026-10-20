# El tercer cargador (L3, ejercicio opcional)

Este ejercicio es **opcional**. La parte guiada del L3 pide construir el cargador dlt del PMS
(`platform/el/src/atlantida_el/fuente_api.py`); este es el ejercicio que la amplía: un cargador
**sin dlt** que cumpla el mismo contrato de carga. Es el ejercicio 2, «Sustituir dlt», del
capítulo 14 del libro («Herramientas por fase y criterios de elección»), llevado a código.

`cargador.py` es un esqueleto: su docstring describe el contrato (esquema `raw_lab`, columnas de
`/v1/tablas`, `_loaded_at`, `_origen = 'lab3'`, *upsert* por la clave, tablas que se releen
enteras, cursor en `raw_lab._cursor`, registro en `meta.carga` con `fuente = 'lab3'` y qué hacer
ante un 409). `main` ya está escrita; completa las funciones que lanzan `NotImplementedError`.
Solo usa `httpx` y `psycopg`, que ya están en la imagen `elt`.

Desde `platform/`:

| Orden | Qué hace |
|---|---|
| `make l3-cargador` | Ejecuta `cargador.py` dentro del contenedor `elt` (con `../laboratorio` montado de solo lectura). `make l3-cargador REINICIAR=1` vacía antes `raw_lab` y sus cursores. |
| `make l3-comprobar` | Ejecuta el cargador dos veces y comprueba el contrato con el comprobador del kit: esquema, linaje, registro, idempotencia y equivalencia con `raw_pms` (lo que cargó dlt) hasta el corte común. |

Para comparar con `raw_pms`, carga antes el PMS con dlt (`make el`). El ejercicio está completo
cuando `make l3-comprobar` termina sin errores dos veces seguidas mientras el PMS del profesor
sigue cambiando.
