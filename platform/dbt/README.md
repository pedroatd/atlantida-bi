# atlantida-dbt: el almacén

## Qué es

Proyecto dbt `atlantida`: SQL versionado y probado que transforma la capa `raw` (cargada por
`platform/el/README.md`) en el almacén analítico. dbt solo transforma: lee y escribe dentro del DWH.
Cada capa vive en su esquema de PostgreSQL:

Términos: un **mart** es una tabla ya preparada para un uso concreto (un perfil de usuario o un
informe); *staging* es la primera capa de limpieza sobre los datos cargados. El resto de conceptos
se explican en los capítulos de modelado dimensional, de calidad y de capa semántica.

| Capa | Esquema | Qué contiene |
|---|---|---|
| Staging | `staging` | Una vista o tabla por tabla de origen: nombres en español, tipos limpios y datos personales seudonimizados. |
| Snapshots | `snapshots` | Historia de los cambios (SCD2) de hoteles, huéspedes y reservas. |
| Intermedia | `intermediate` | Pasos de cálculo reutilizables: golden record, reservas, periodos… |
| Modelo dimensional | `marts_core` | Dimensiones, hechos, tabla puente, agregado. |
| Marts por actor | `marts_revenue`, `marts_marketing`, `marts_experiencia` | Tablas listas para cada perfil de usuario. |
| KPI | `marts_kpi` | Indicadores con una sola definición y objetivos con su índice de logro. |
| Data Vault | `vault` | Modelo alternativo (hubs, links y satélites), en paralelo al dimensional. |

`staging` y el resto los escribe el rol `transformer`; el rol de solo lectura `bi_reader` consulta
los marts pero **no** `raw_pms`.

## Parámetros del semáforo y perfil de lectura

El semáforo de aspectos (días con un aspecto en rojo) lee sus parámetros (ventana, umbral,
menciones mínimas, huecos máximos y modelo de IA oficial) de `platform/definicion/atlantida.yml`:
no hay constantes en el SQL. El perfil `perfiles/lectura` lo usan la capa semántica y el texto a
SQL de la IA: conecta como `bi_reader`, en sesiones de solo lectura y con límite de tiempo, para
que nada de lo que ejecute una pregunta de un usuario o de un modelo pueda modificar el almacén.

## Cómo se ejecuta

Desde `platform/`:

| Orden | Qué hace |
|---|---|
| `make pipeline` | Carga incremental y `dbt build` completo. Se puede repetir sin duplicar nada. |
| `make dbt ARGS="build --select marts.kpi"` | Construye solo una parte (modelos y sus pruebas). El criterio es el nombre del modelo o la ruta con puntos (`marts.kpi` es la carpeta `models/marts/kpi`). Si no selecciona nada, `atlantida-dbt` lo dice y termina con error; con `make dbt ARGS="ls --select marts.kpi"` ves qué incluye. |
| `make dbt ARGS="test"` | Ejecuta todas las pruebas. |
| `make historico` | **Destructiva** y del profesor (necesita el simulador del PMS; la edición del alumnado no la trae), ver su sección. |


Con uv, fuera de Docker, desde la raíz: `uv run atlantida-dbt dbt build` (con las variables `DWH_*` de
`platform/.env`). Tras cambiar `platform/definicion/atlantida.yml`, ejecuta
`uv run atlantida-dbt generar` para regenerar los ficheros derivados.

### Cuánto tarda

A escala 1, en un equipo de sobremesa (12 hilos, WSL2), la primera ejecución de `make pipeline` tarda
unos 12,5 minutos: unos 10 de cargas y unos 2,5 de `dbt build`. Repetida sin cambios en el PMS,
unos 3 minutos, casi todos de `dbt build`. Se midió cuando `make pipeline` aún no clasificaba las
reseñas ni aplicaba los paneles; hoy, con todo, unos 25 minutos la primera vez y unos 4,5 las
siguientes (README raíz). Mientras construye, el DWH llega a unos 4,5 GB de RAM
según `docker stats` (incluida su caché) y ocupa unos 5,6 GB de disco. A escala 0,02, la primera
ronda los 7,5 minutos y las repeticiones, unos 46 segundos. Son medidas orientativas, no
garantías; el detalle está en `platform/el/README.md`.

## Convenciones de nombres

Los marts y los KPI se nombran en español y `snake_case`. El PMS está en inglés porque es el sistema
de origen tal como lo diseñaría un proveedor; el almacén está en español porque es lo que leerán
quienes analizan. `staging` hace la traducción.

| Prefijo | Significado |
|---|---|
| `stg_pms__`, `stg_ext__` | Staging del PMS y de las fuentes externas. |
| `snp_` | Snapshot (historia SCD2). |
| `int_` | Intermedio. |
| `dim_`, `fct_`, `brg_`, `agg_`, `mv_` | Dimensión, hecho, tabla puente, agregado, vista materializada. |
| `kpi_`, `objetivo_` | KPI y objetivos. |
| `rev_`, `mkt_`, `exp_` | Marts de revenue, marketing y experiencia. |
| `hub_`, `lnk_`, `sat_` | Data Vault. |

Las fechas se expresan en hora local de Canarias (`Atlantic/Canary`).

## Staging y datos personales

`staging` traduce nombres de tablas y columnas y normaliza tipos. Además, **seudonimiza** los datos
personales de los huéspedes (nombre, apellidos, correo, teléfono, documento y fecha de nacimiento):
guarda el SHA-256 (una función *hash*: de un valor obtiene siempre la misma huella, y de la huella no se puede volver al valor directamente) de una sal (un texto secreto que se añade antes de calcularla) y del valor normalizado, y unas claves de comparación también
seudonimizadas para poder decidir si dos fichas son la misma persona sin ver sus datos. Esos datos
solo existen en claro en `raw_pms`, que `bi_reader` no puede leer.

Un seudónimo **sigue siendo dato personal** (RGPD, art. 4.5): se puede volver a relacionar con la
persona si se conoce la sal o se prueban valores. No es anonimización.

### La sal de los seudónimos es secreta

La sal (`DWH_SEUDONIMO_SAL`) la genera `make` al crear `.env` y no la muestra. Quien la conozca puede
recuperar por fuerza bruta los campos con pocas posibilidades (fecha de nacimiento, teléfono,
documento, nombre). Por eso:

- no la compartas ni la copies a otro sitio; cambiarla cambia todos los seudónimos y, con ellos,
  las fichas ya guardadas (el snapshot de huéspedes y el satélite del vault guardarían las dos
  sales). Por eso `make pipeline` guarda una huella de la sal (nunca la sal) y **se niega a seguir**
  si cambia, con instrucciones (también `make dbt` cuando construye: `build`, `run`,
  `snapshot`). Si fue un error, vuelve a poner la sal anterior en `.env` (no borres el fichero);
  si la cambiaste a propósito, empieza de cero con `make pipeline REINICIAR=1` (rehace esas fichas
  con la sal nueva) o con `make historico`;
- la sal no se escribe en el SQL: `atlantida-dbt` (y Dagster) la pasan en cada conexión como
  parámetro de sesión (variable `PGOPTIONS`; también en `DBT_ENV_SECRET_SAL`, cuyo valor dbt borra
  de sus registros) y el SQL la lee con `current_setting('atlantida.sal')`. Llega por la conexión: no aparece en
  `target/`, `logs/` ni en el catálogo de PostgreSQL. Aun así, `target/` y `logs/` no se versionan
  ni entran en las imágenes;
- sin sal, con un valor de ejemplo o con caracteres que no sean letras sin tilde, dígitos, `_` o
  `-` (al menos 8), dbt se detiene; si se lanza `dbt` a mano, sin `atlantida-dbt`, el modelo que
  seudonimiza también se detiene.

## Entornos dev y prod

`make dbt` trabaja por defecto en `prod` (los esquemas del almacén). Para probar un cambio sin tocarlo:

```bash
make dbt ENTORNO=dev ARGS="build --select state:modified+"
```

Construye en esquemas `dev_*` solo los modelos modificados y lo que depende de ellos; el resto se lee del
almacén de producción (`--defer`, con el *manifest* de la última construcción).


## SCD2 y `make historico`

Una **SCD2** (*slowly changing dimension* tipo 2) guarda una fila por cada versión de un dato, con
el intervalo en que fue vigente. Un snapshot de dbt compara cada ejecución con la versión vigente y,
si la fila cambió, la cierra y abre otra. La primera versión de cada fila vale desde 1900-01-01.

Tras la primera carga (`make pipeline`), cada fila tiene **una sola versión**: el PMS ya está en
su estado de ese momento y no hay cambios que registrar. Verás versiones nuevas cuando el PMS cambie
entre dos ejecuciones (por ejemplo, con la simulación viva en marcha).

### `make pipeline` frente a `make historico`

- `make pipeline` es seguro: carga lo nuevo y reconstruye el almacén. Puedes repetirlo.
- `make historico` **es destructivo** y solo existe en la edición completa, la del profesor (en la
  del alumnado, `make historico` lo explica y termina). Pide confirmación y entonces:
  - detiene la simulación viva;
  - **borra y vuelve a sembrar todo el PMS** (también los datos escritos por reverse ETL);
  - **borra y vuelve a cargar todo el DWH** (incluidos los snapshots anteriores);
  - reproduce el pasado paso a paso (`PASO=mes|trimestre|semestre`, por defecto `mes`), cargando y
    ejecutando `dbt snapshot` en cada corte, para que los snapshots tengan la historia completa.

  A escala 1 tarda unos 30 minutos con `PASO=mes` (medido en un equipo de sobremesa) y llega a
  unos 8 GB de RAM entre todos los contenedores. Úsalo solo cuando quieras practicar con la
  historia de los cambios. Si se interrumpe, repítelo. Con `ESCALA=0.1` (`make historico ESCALA=0.1`)
  reconstruye a esa escala; sin ella usa `SIM_ESCALA` de `.env`, y la orden muestra la escala
  antes de pedir confirmación. Para usarlo sin preguntar (en un guion), `make historico CONFIRMAR=1`.

## Golden record (MDM)

Una misma persona puede estar registrada varias veces en el PMS, con variaciones en sus datos. La gestión de datos maestros (**MDM**) las
unifica en un *golden record*:

1. **Reglas de coincidencia:** dos fichas son la misma persona si comparten documento, o correo o
   teléfono junto con el nombre o la fecha de nacimiento, o nombre y fecha de nacimiento. Todo se
   compara con las claves seudonimizadas.
2. **Bloqueo por frecuencia:** una clave compartida por demasiadas fichas no sirve para identificar
   a nadie y se descarta.
3. **Cierre transitivo:** si A coincide con B y B con C, las tres son la misma persona.
4. **Supervivencia:** para cada atributo se elige qué valor sobrevive (el más frecuente, el de la
   ficha más reciente, «basta con que una ficha lo tenga», etc.).

La pertenencia de una ficha a un grupo es de **tipo 1**: se recalcula en cada ejecución. Solo el
**segmento** del huésped tiene historia SCD2 en `dim_huesped`.

## Modelo dimensional

Un **hecho** es una tabla de medidas de un proceso (reservas, noches, cargos…) y una **dimensión** es
una tabla de contexto para describirlas (fecha, hotel, canal…). El **grano** es lo que representa una
fila del hecho; véase el capítulo de modelado dimensional. Hechos de `marts_core`:

| Hecho | Tipo | Grano |
|---|---|---|
| `fct_reserva` | transacción | una fila por reserva |
| `fct_noche_estancia` | transacción | una fila por noche y habitación ocupada |
| `fct_cancelacion` | transacción | una fila por cancelación |
| `fct_resena` | transacción | una fila por reseña |
| `fct_coste` | transacción | una fila por apunte de coste |
| `fct_cargo_folio` | transacción (incremental) | una fila por cargo de folio |
| `fct_estancia_huesped` | transacción | una fila por estancia finalizada del titular |
| `fct_ocupacion_diaria` | snapshot periódico | una fila por hotel y día |
| `fct_compset_diario` | snapshot periódico | una fila por hotel y día (competencia) |
| `fct_ciclo_reserva` | snapshot acumulativo | una fila por reserva, actualizada con sus hitos |

Técnicas que encontrarás en las dimensiones:

- **Dimensión de rol:** `dim_fecha` se usa varias veces en un hecho con papeles distintos (reserva,
  llegada, salida…).
- **Dimensión degenerada:** `localizador`, un identificador que vive en el hecho sin tabla propia.
- ***Junk*:** `dim_indicadores_reserva` agrupa banderas sueltas en una sola dimensión.
- **Mini-dimensión:** `dim_perfil_huesped` separa los atributos del huésped que cambian a menudo.
- **Jerarquía irregular:** `dim_canal` (canales con distintos niveles de profundidad).
- **Tabla puente:** `brg_reserva_huesped` relaciona reservas y huéspedes (varios por reserva); lleva
  `es_titular` y `factor_ponderacion` para no contar dos veces.
- **Miembros especiales:** `-1` es «desconocido»; en campañas, `-2` es «no aplica».
- **Hechos que llegan tarde:** un hecho puede registrarse después del momento al que pertenece; se
  modela imputándolo a su fecha real y reprocesando un margen reciente en un modelo incremental.
- **Agregado y vista materializada:** `agg_noches_hotel_mes` y `mv_rendimiento_mensual`.

## KPI: una sola definición

Los indicadores se definen **una sola vez**, en `platform/definicion/atlantida.yml`. De ahí,
`atlantida-dbt generar` produce la macro `formulas_kpi()` que usan los marts y las métricas derivadas
de la capa semántica: ningún modelo escribe a mano la fórmula de un KPI. Una prueba falla si los
ficheros generados están desactualizados.

- Las métricas con **madurez** (las que dependen de que las reservas hayan tenido tiempo de
  resolverse) se miden por fecha de reserva y solo se consideran firmes cuando su periodo ha
  madurado.
- `objetivo_logro` calcula el índice de logro y el semáforo de cada objetivo y debe coincidir con
  `atlantida_def.logro`; compruébalo con `uv run atlantida-dbt logro`.
- **Regla de datos faltantes:** si a un objetivo le falta el dato de algún criterio, su resultado
  solo se calcula cuando no depende de ese dato; si depende, queda sin valor y el semáforo marca
  `sin_datos`. La columna `datos_completos` indica si todos los criterios tenían dato y madurez.
- La línea base se calcula en el propio almacén, con el periodo base.

Tras `make pipeline` puedes consultar los objetivos con `make psql-dwh`:

```sql
select objetivo_id, evaluacion, ambito, indice, semaforo, datos_completos
from marts_kpi.objetivo_logro
order by objetivo_id, evaluacion
limit 20;

select fecha, ambito, kpi, valor
from marts_kpi.kpi_diario
where kpi = 'revpar'
order by fecha desc
limit 10;
```

El KPI **mensual** (y el acumulado del año) está en `marts_kpi.kpi_periodo`: una fila por
`kpi`, `ambito`, `periodo_id` (`2025-08` para un mes) y `tipo_periodo` (`mes` o `ytd`), con
`completo` para saber si el periodo está cerrado. `ambito` es el código del hotel (consúltalo en
`marts_core.dim_hotel`) o `CADENA` para el total.

```sql
select periodo_id, ambito, valor, completo
from marts_kpi.kpi_periodo
where kpi = 'revpar' and ambito = 'TFN' and periodo_id = '2025-08';
```

**No promedies `kpi_diario` para obtener el KPI del mes**: la ocupación, el ADR o el RevPAR son
cocientes, y el promedio de cocientes diarios no es el cociente del periodo (pesa igual un día
con pocas habitaciones disponibles que otro con muchas). `kpi_periodo` ya lo calcula como suma
entre suma.

## Calidad

Hay pruebas genéricas (únicos, no nulos, relaciones), singulares (`pruebas/`), de unidad y contratos
de columnas en los hechos y los KPI. Las pruebas con la etiqueta `defectos_origen` **avisan**
(`warn`, no fallan) de problemas de los datos de origen que el almacén corrige o hace visibles. Mira
los avisos con:

```bash
make dbt ARGS="test --select tag:defectos_origen"
```

y averigua qué hay detrás: es parte del trabajo del curso.


## Marts por actor

| Mart | Para quién |
|---|---|
| `rev_rendimiento_diario` | Revenue manager: rendimiento diario y posición frente a la competencia. |
| `rev_cancelacion_segmentos` | Revenue manager: cancelación por cohorte y segmento. |
| `rev_pickup` | Revenue manager: pickup diario por hotel. |
| `mv_rendimiento_mensual` | Dirección y revenue: rendimiento mensual precalculado, con `completo` (mes ya maduro); sin cierre contable, GOPPAR nulo. |
| `mkt_mix_canal_mensual` | Marketing: mezcla de canales. |
| `mkt_captacion_semanal` | Marketing: cuota directa de captación y campañas, con el estado actual de las reservas (`*_actual`, no el KPI maduro de `marts_kpi`). |
| `mkt_cac_mensual` | Marketing: coste de adquisición por reserva neta, con `completo`; sin cierre contable, CAC nulo. |
| `exp_nps_mensual` | Direcciones de hotel: NPS por mes, hotel y fuente. |
| `exp_repeticion_mensual` | Marketing y direcciones de hotel: repetición de huéspedes. |
| `exp_aspectos_diario` | Direcciones de hotel: semáforo de aspectos de las reseñas. |
| `exp_incidencias` | Direcciones de hotel: incidencias por día (habitaciones fuera de servicio, aspectos en rojo y días anómalos). |
| `rev_precios_diarios` | Revenue manager: precio medio por día, hotel y tipo de habitación frente al *compset* (índice de tarifa media, 100 = paridad). |
| `rev_tarifas_mercado` | Revenue manager: tarifas de la competencia por fecha de estancia (mínima, mediana y máxima del mercado). |
| `rev_ocupacion_tipo` | Revenue manager: ocupación por tipo de habitación (lo que el panel llama «cupos»: el PMS no registra *allotments*). |
| `rev_prevision_vigente` | Revenue manager: previsión de ocupación oficial del último origen de cada hotel (vacía hasta que la capa de IA publique su previsión). |
| `mkt_cuota_mercado_istac` | Marketing: cuota de mercado por isla, mes y mercado emisor frente a las llegadas del ISTAC. |
| `mkt_valor_huesped` | Marketing y direcciones de hotel (acción A7): valor de cada huésped del *golden record*, si es de alto valor y su grupo (tratamiento o control). |
| `mkt_marca_huesped` | Marketing y direcciones de hotel: marcas de huésped del PMS (del simulador y del *reverse ETL*) sobre el *golden record*. |
| `mkt_fidelizacion` | Marketing (acción A3): pertenencia al programa de fidelización por huésped del *golden record*. |

Los marts de huéspedes solo llevan identificadores seudónimos.

