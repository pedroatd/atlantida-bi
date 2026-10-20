# atlantida-def

Definición del sistema de BI de **Atlántida Hoteles** como código. Este paquete es la
**fuente única de verdad** de los objetivos, actores, medidas, métricas base, KPI, acciones
y hoteles del caso: los capítulos del libro generan sus tablas a partir de él, los modelos
dbt y los cuadros de mando Dash calculan el mismo índice de logro y el simulador
del PMS lee de aquí los hoteles, el horizonte simulado, la desagregación de los paquetes,
el calendario de las acciones y el vocabulario de reverse ETL (véase «Interfaces para el simulador y las fuentes»).

## Ficheros

| Fichero | Contenido |
|---|---|
| `contrato_pms.yml` | Esquema del PMS (`pms-db`, esquema `public`): las 21 tablas de C3 con sus columnas (más `created_at` y `updated_at`) y, en `restricciones`, los valores permitidos de cada enumeración, incluido el vocabulario de reverse ETL (`guest_flag.flag`, `rate_restriction.rule`). El DDL del simulador se valida contra él. |
| `contrato_externo.yml` | Fuentes externas (especificación §2.4): por fuente, columnas `claves` (grano) y `valores`. El compset se separa en `rate_shopper` (tarifas por competidor) y `compset_diario` (informe tipo STR). Los descargadores de fuentes producen exactamente estas columnas. |
| `atlantida.yml` | Documento de definición: hoteles, actores, medidas raw, métricas base, KPI, objetivos con sus criterios, acciones, periodos y umbrales del semáforo. |
| `src/atlantida_def/modelos.py` | Modelo pydantic de cada bloque y validación de integridad referencial. |
| `src/atlantida_def/carga.py` | `cargar_contrato`, `cargar_contrato_externo`, `cargar_restricciones` y `cargar_definicion` (valida la definición y la contrasta con los dos contratos). |
| `src/atlantida_def/logro.py` | Índice de logro de un objetivo, semáforo, «logrado», evaluación con datos incompletos (`evaluar_objetivo_parcial`) y ventanas del seguimiento mensual (`ventanas_ytd`). |
| `tests/` | Pruebas del índice, de la carga y de la definición real. |

## Uso

```python
from atlantida_def import cargar_definicion, evaluar_objetivo

d = cargar_definicion()                       # atlantida.yml, desde cualquier directorio
o1 = next(o for o in d.objetivos if o.id == "O1")
r = evaluar_objetivo(o1, {"revpar": (92.0, 97.5), "goppar": (31.0, 32.4), "adr": (118.0, 120.0)},
                     d.semaforo)
r.indice, r.semaforo                          # (0.7473, 'ambar')
```

Las rutas por defecto no dependen del directorio de trabajo: los YAML se buscan junto al
paquete (van dentro de la rueda) o, en la instalación editable del *workspace*, en este
directorio. El libro, que se renderiza con `book/` como directorio de trabajo, los
encuentra igual.

## Esquema de `atlantida.yml`

Cadena de trazabilidad: **medida raw → métrica base → KPI → criterio de un objetivo → acción**.

- `periodo_base` (2024) y `periodo_evaluado` (2025); `semaforo` (umbrales `verde` y `ambar`);
  `seguimiento` (`frecuencia`: `mensual`; `comparacion`: `ytd_vs_ytd_base`, véase «Índice de
  logro»); `horizonte_simulado` (`inicio`, `fin`: histórico simulado, 2023-01-01 →
  2026-03-31; debe cubrir el año base, el evaluado y la evaluación de cada acción;
  `historia_huespedes_desde`: 2022-01-01, desde cuándo hay estancias de huéspedes);
  `desagregacion_regimen` (por régimen de `rate_plan.board`, parte del precio del paquete que
  es alojamiento; `RO` = 1; las claves se contrastan con el contrato).
- `hoteles`: `codigo` (3 letras), `nombre`, `isla`, `municipio`, `tipo` (`urban`, `resort`,
  `all_inclusive`, `rural`, como `hotel.hotel_type`), `estrellas`, `habitaciones`.
- `actores`: `id`, `nombre`, `nivel`, `frecuencia`, `necesidad` y los `kpis` que consulta.
  Cada KPI cita a sus actores y cada actor a sus KPI; ambas listas deben coincidir.
- `medidas_raw`: hechos tal como se registran. `fuente: pms` exige que `tabla.columna`
  exista en el contrato del PMS; `fuente: externa`, que `tabla` sea una fuente de
  `contrato_externo.yml` y `columna` una de sus claves o valores (`istac_frontur`,
  `aemet_diario`, `festivos`, `bce_tipos`, `rate_shopper`, `compset_diario`).
- `metricas_base`: agregados por hotel y periodo; `formula` explica en texto cómo se
  obtienen de sus `medidas`; `agregacion` dice cómo se combinan entre hoteles y periodos,
  porque no todas son aditivas: `suma`, `distintos` (huéspedes distintos: se recalculan
  sobre el conjunto), `maximo` (días en rojo) o `publicado` (cifras del informe del
  compset: se usan tal cual o ponderadas). La `descripcion` opcional recoge convenciones y supuestos
  (por ejemplo, que los costes operativos incluyen las comisiones de canal, como en USALI).
  Las medidas marcadas como «clave de unión» son las columnas por las que se enlazan las
  tablas al calcular la métrica.
- `kpis`: `formula` es una expresión que usa **solo** identificadores de métricas base
  (y la función `max`); el validador comprueba que coinciden con `metricas`. Las fórmulas
  reproducen la tabla C5 de la hoja de ruta. `definicion` es la explicación para el
  alumnado; `sentido` dice si mejorar es `subir` o `bajar`, o es `neutro` en los
  indicadores de diagnóstico (antelación media, estancia media), que no pueden ser
  criterio principal de un objetivo. `actores` son quienes lo consultan; `propietario` es el
  actor de negocio que responde de su definición y resultado (debe estar entre sus
  `actores`; el equipo de datos custodia el cálculo de todos pero no es propietario de
  ninguno), y `latencia` dice cuándo está disponible el dato (por ejemplo, «D-1, a las
  07:00» o «Mensual, al cierre contable»). La latencia va en el KPI y no en el actor
  porque depende de la fuente (el informe del compset es semanal; los costes, mensuales),
  no de quién lo mira; la `frecuencia` del actor ya dice cada cuánto decide.
- `objetivos`: `verbo`, `enunciado`, `responsable` (actor que responde del objetivo; debe
  consultar todos los KPI de sus criterios), `linea_base` (valor de cada KPI de los criterios
  en el periodo base, calculado en el almacén con los datos de 2024; `null` mientras falte
  alguno: no se inventa)
  y `criterios`. Cada criterio tiene un `papel`
  (`principal`, con `peso`; o `guardarrail`, sin peso) y una `comparacion`
  (`tipo`, `sentido`, `meta`). Los pesos de los principales suman 1; un KPI no se repite
  dentro de un objetivo; en un principal, el sentido del criterio concuerda con el del
  KPI (`al_menos` ↔ `subir`, `como_maximo` ↔ `bajar`) y, si es una variación, la meta es
  una mejora (`al_menos` con meta > 0, `como_maximo` con meta < 0). Los guardarraíles
  admiten cualquier signo: «el ADR no cae más de un 3 %» es `al_menos -0.03`.
- `acciones`: objetivos a los que contribuye, `disparador` (el insight), `descripcion`,
  `responsable` (un actor), `kpi_exito` y `criterio_exito`, `guardarrailes`,
  `ventana_dias`, `inicio` y `fin` (la intervención; `fin: null` si sigue activa; `inicio`
  cae en el periodo evaluado), `evaluacion` (`base`: `llegada`, `reserva`, `estancia` o
  `publicacion`, la fecha que sitúa cada hecho; `desde` y `hasta`, incluidos, con
  `hasta − desde + 1 = ventana_dias` y `desde ≥ inicio`; `corte`, la fecha en que se leen los
  datos, `≥ hasta`, al menos 30 días después con base `reserva` y dentro del horizonte
  simulado; `reservas_desde` opcional, para contar solo las reservas creadas desde una
  fecha), `metodo_evaluacion`, `ambito` (y, si
  procede, `hoteles_piloto` y `hoteles_control`) y `mecanismo` (`manual` o `reverse_etl`;
  en este caso es obligatoria `regla_pms`: `tabla` —`guest_flag` o `rate_restriction`—,
  `valor` —del vocabulario del contrato— y `parametro` —antelación mínima en días o
  noches mínimas; obligatorio en `rate_restriction`, prohibido en `guest_flag`—, y la descripción nombra la tabla y el valor).
  Solo en `guest_flag`, `regla_pms.seleccion` dice a quién se marca: `percentil_valor` (se
  marcan los huéspedes del *golden record* con valor en ese percentil o superior; valor =
  importe en EUR de las reservas no canceladas de las que es titular en los últimos
  `meses_valor` meses) y `fraccion_control` (parte de esos huéspedes que no se marca, elegida
  con un hash del *golden record* y la sal secreta del almacén, `mkt_grupo_a7`: el grupo de
  control, reproducible en el almacén y no predecible con el id). `atlantida-dbt generar`
  los lleva a la semilla `def_parametro` (`accion_<id>_<campo>`).
- `alertas`: reglas de alerta sobre los KPI, con `id` (`AL1`, `AL2`…), `nombre`, `tipo`,
  `kpi`, `ambito` (`hotel` o `cadena`), `destinatario` (un actor que consulta el KPI) y
  `accion` opcional (una acción con mecanismo `reverse_etl`: si la alerta salta, su
  `regla_pms` se escribe en el PMS). Tipo `umbral`: exige `periodo` (`mes`, el último mes
  cerrado), `sentido` (`por_encima` o `por_debajo`) y `umbral`. Tipo `deterioro`: exige
  `periodo`, `sentido` y `margen` (sin `umbral`); salta si el KPI del último mes cerrado empeora
  más del margen frente al mismo mes del año anterior del propio ámbito. Las dos admiten
  `muestra_minima` (`metrica`, una métrica base del KPI, y `minimo`): con menos unidades en el
  mes o en su referencia no saltan. Un valor igual al umbral, salvo el ruido de coma flotante,
  un mes sin dato o sin referencia no disparan (`atlantida_def.alertas.dispara`).
  Tipo `anomalia`: un día marcado en `ml.anomalia_kpi`; solo para los KPI diarios
  (`KPI_DIARIOS`), sin umbral ni acción (solo avisa). Las evalúa y ejecuta `platform/accion`
  (`make alertas`, `make accion`, el sensor `alertas_kpi` de Dagster; `MES=AAAA-MM` evalúa las
  reglas mensuales en otro mes cerrado); la selección de
  `regla_pms.seleccion` la aplica su *reverse ETL* al marcar a los huéspedes de A7. Guía en
  `platform/accion/README.md`.

- `metricas_base` y `acciones` admiten una `nota_docente` opcional: una nota para el libro
  (por ejemplo, el capítulo que construye una pieza o usa la acción como lección). El
  documento de la organización no la muestra; el resto de textos no citan capítulos.
- `supuestos`: `id`, `nombre` y `texto`: decisiones de diseño que cambian una cifra (las
  metas no se repiten en ellos: viven solo en las comparaciones).
- `riesgos`: `id`, `nombre`, `efecto`, `mitigacion` y `responsable` (un actor).
- `documento`: control del documento, con `propietario` y `custodio` (actores), `estado`
  (`borrador`, `en_revision` o `aprobado`; aprobado exige `fecha_aprobacion`),
  `revision_ordinaria`, `revision_extraordinaria` e `historial` (`version`, `fecha`,
  `cambio`, `aprobado_por`), en orden cronológico y terminado en la versión vigente
  (`version`). La fecha de aprobación de Atlántida es ficticia y anterior al periodo
  evaluado.

Ningún identificador puede repetirse y todo identificador citado debe existir; los campos
desconocidos son un error (una errata en una clave no pasa en silencio).

## Índice de logro

Para cada criterio, con el valor del KPI en el periodo base (`base`) y en el evaluado
(`actual`), se calcula la magnitud comparada `x`:

| `tipo` | `x` |
|---|---|
| `variacion_relativa` | `actual / base − 1` (error si `base == 0`) |
| `variacion_absoluta` | `actual − base` |
| `umbral` | `actual` |

El criterio **se cumple** si `x >= meta` (`al_menos`) o `x <= meta` (`como_maximo`), con
una tolerancia absoluta de `1e-9` (`TOLERANCIA` en `logro.py`) a favor del cumplimiento:
en coma flotante `97 / 100 − 1 = −0.030000000000000027`, y sin ella un ADR que cae
exactamente un 3 % incumpliría «no caer más de un 3 %». La misma regla decide cuándo el
progreso de un principal es 1.

El **progreso** `p` de un criterio principal está entre 0 y 1:

- si el criterio se cumple, `p = 1` (en todos los tipos);
- si no se cumple y es un umbral, `p = clamp((actual − base) / (meta − base), 0, 1)`, la
  fracción del camino recorrido desde la línea base; pero si el umbral no estaba por
  delante de la base (`al_menos` con `meta ≤ base`, `como_maximo` con `meta ≥ base`), la
  base ya cumplía y se ha retrocedido: `p = 0`;
- si no se cumple y es una variación, `p = clamp(x / meta, 0, 1)`; pero si `meta == 0` o
  su signo contradice el sentido (`al_menos` con meta negativa, `como_maximo` con meta
  positiva), `p = 0`. Una reducción se expresa con meta negativa y `como_maximo`
  (−25 % → `meta: -0.25`).

Ejemplos: NPS `al_menos 45` con base 48 y actual 44 → `p = 0` (antes cumplía, ahora no);
tasa de cancelación OTA `como_maximo 0.18` con base 0.26 y actual 0.22 → `p = 0.5`.

**Índice** = `Σ peso · p` sobre los principales. Los guardarraíles no suman; solo se
comprueba que se cumplen. **Semáforo** (umbrales en `semaforo`): verde si
`índice >= verde` y todos los guardarraíles se cumplen; rojo si `índice < ambar`; ámbar en
otro caso. Un guardarraíl incumplido nunca da verde.

**Logrado frente a verde.** Un objetivo está **logrado** si su índice es 1 (todos los
principales cumplen su meta) **y** se cumplen todos los guardarraíles
(`ResultadoObjetivo.logrado`); está **verde** si el índice llega al umbral verde y se
cumplen los guardarraíles. Todo logrado es verde, pero no al revés: un 0,95 con los
guardarraíles cumplidos es verde y no está logrado.

**Datos incompletos** (`evaluar_objetivo_parcial`). Un criterio no tiene dato si le falta
la base o el valor actual (también en un umbral, porque el progreso necesita la base) o si
es una variación relativa sobre una base 0. Su magnitud, cumplimiento y progreso quedan
vacíos. Del objetivo solo se da lo que no depende de esos datos. Para saberlo, se evalúa con
los dos extremos de cada dato que falta (cumple con progreso 1, o incumple con progreso 0).
Un resultado que coincide en todas las combinaciones se da; si no, queda vacío, y el
semáforo es `sin_datos`. Ejemplo: sin el dato de un guardarraíl, un índice por debajo de
ámbar es rojo de todos modos, y uno por encima de verde queda `sin_datos`. El almacén
(`marts_kpi.objetivo_logro`) aplica esta misma regla.

**Seguimiento mensual** (`seguimiento`: `mensual`, `ytd_vs_ytd_base`). Cada mes, al cierre,
se calcula el índice con el acumulado del año en curso hasta ese mes frente al mismo tramo
del año base. `ventanas_ytd(periodo_evaluado, periodo_base, mes)` devuelve las dos ventanas
(mes cerrado frente a mes cerrado: febrero de 2024 llega al día 29). La evaluación anual es
la del cierre de diciembre.

## Decisiones de la revisión de la versión 2.0.0

Registradas en `documento.historial` y en `supuestos` (S1–S17):

- **Cancelación por cohorte de llegada.** `tasa_cancelacion` y `tasa_cancelacion_ota` cuentan
  las reservas con llegada en el periodo: al cierre del periodo están todas resueltas, así que
  un mes cerrado es maduro. No se conserva la variante por fecha de creación
  (`tasa_cancelacion_creacion`): ningún criterio ni actor la necesita; si se añade, debe
  llevar ese nombre y no usarse en criterios.
- **Ingreso perdido neto normalizado**, por cohorte de llegada y en proporción del ingreso de
  habitaciones reservado para esas llegadas. La meta (−25 % relativa) se mantiene: reducir en
  una cuarta parte la proporción perdida sigue siendo una meta con sentido y ya no depende del
  volumen vendido.
- **Base STR para el benchmarking**: `habitaciones_disponibles_str` (todo el inventario) en MPI y
  RGI; el ARI no usa habitaciones disponibles. Los KPI internos siguen con
  `habitaciones_disponibles` (sin fuera de servicio).
- **Guardarraíles nuevos**: O3, ocupación (variación absoluta, mismo margen que O2); O2, GOPPAR
  que no baja. Es una desviación respecto a la especificación §2.1, enmendada allí.
- **Responsables**: O1 dirección general (RevPAR con GOPPAR de guardarraíl es la cuenta de
  resultados de la cadena, que cruza departamentos); O2 marketing (canales y campañas);
  O3 revenue (condiciones de venta y depósitos); O4 direcciones de hotel (la experiencia se
  entrega en la operación). Como el responsable debe consultar los KPI de su objetivo, se
  añaden a la matriz: ADR a dirección; ocupación y GOPPAR a marketing; tasa de repetición a
  las direcciones de hotel.
- **Comisiones al devengo** (por `stay_night`, tipo pactado en `booked_at`). El CAC divide esas
  comisiones entre las reservas netas creadas en el periodo: los calendarios no coinciden
  dentro de un mes, pero sí en el año y en la base.
- **Cuota directa de captación** (por `booked_at`) como KPI de éxito de A2; O2 conserva la cuota
  por fecha de estancia.
- **Repetición**: otra estancia en los 24 meses anteriores (ventana fija, igual en base y
  evaluado); cuenta también una estancia previa dentro del periodo.
- **Calendario** (intervención; evaluación):

  | Acción | Intervención | Evaluación (`base`, `desde` → `hasta`, `corte`) |
  |---|---|---|
  | A1 | 2025-03-01, sigue activa | llegada, 2025-04-30 → 2025-08-27 (solo reservas creadas desde 2025-03-01), corte 2025-08-27 |
  | A2 | 2025-06-01 → 2025-08-31 | reserva, 2025-06-01 → 2025-08-29, corte 2025-09-28 |
  | A3 | 2025-03-01, permanente | llegada, 2025-03-01 → 2026-02-28 (ciclo anual) |
  | A4 | 2025-07-01 → 2025-08-31 | publicación de reseñas, 2025-07-01 → 2025-09-28 |
  | A5 | 2025-09-01, sigue activa | estancia, 2025-09-01 → 2025-11-29 (antes de A6) |
  | A6 | 2025-12-01 → 2026-02-28 | estancia, 2025-12-01 → 2026-02-28 |
  | A7 | 2025-04-01, sigue activa | publicación de reseñas, 2025-04-01 → 2025-09-27 |

  A1 se evalúa por cohorte de llegada a partir de `inicio + 60 días`, porque la regla solo
  afecta a reservas con más de 60 días de antelación, y solo con reservas creadas desde el
  inicio; así la ventana termina dentro del histórico aunque haya reservas con mucha
  antelación. La campaña A2 coincide 88 días (2025-06-01 → 2025-08-27) con esa ventana; el
  solape es explícito en los dos ámbitos.
- **Parámetros de reverse ETL**: A1, `deposito_obligatorio` con antelación mínima 60 días
  (el nombre de la acción); A6, `estancia_minima` con 5 noches (decisión de diseño; la
  especificación no fija la cifra), solo en los cuatro hoteles vacacionales (sol y playa y
  todo incluido): el urbano y el rural tienen estancias cortas por naturaleza.
- **Madurez de las métricas por fecha de reserva** (reservas netas, noches reservadas,
  noches reservadas directas: CAC y cuota de captación): el estado se lee un mes después del
  fin del periodo o de la ventana (`evaluacion.corte`, al menos `MADUREZ_RESERVA_DIAS` = 30
  días después de `hasta` cuando la base es `reserva`).
- **Desagregación de paquetes** (supuesto de diseño, no dato): parte de alojamiento RO 1;
  BB 0,88; HB 0,75; FB 0,65; AI 0,55.
- **Versión 2.0.0** (cambio mayor: cambian definiciones), aprobada el 2025-02-14, antes de la
  primera acción y de fijar la línea base. La 2.1.0 añadió `loyalty_member` (cambio aditivo), la
  2.2.0 acota el ámbito de A3 (alta solo de huéspedes identificables), la 2.3.0 aclara
  reubicaciones, repetición y mercado de Austria y fija la línea base de O1–O3, la 2.4.0 hace
  explícitos los parámetros del semáforo de aspectos, la 2.4.1 fija la línea base de O4 y la
  2.5.0 añadió las alertas sobre KPI (AL1–AL3) y la selección de los huéspedes de A7, la 2.5.1
  cambia AL1 y AL2 a un deterioro frente al mismo mes del año anterior, con margen y muestra
  mínima, y la vigente, 2.5.2, reescribe dos notas para el libro (`nota_docente` de A1 y A6)
  sin cambiar ninguna definición.
  Un cambio de `atlantida.yml` cambia la huella del simulador, salvo en las secciones que no
  cambian ningún dato simulado: `version`, `documento` (historial) y `alertas`
  (`DEFINICION_FUERA_DE_HUELLA`, en el módulo de carga del simulador). Si cambia la huella y ya tenías el
  PMS sembrado, `make -C platform reseed` y después `make -C platform pipeline REINICIAR=1` (el simulador
  vivo se niega a seguir con la huella antigua). Al pasar de la 2.4.1 a la 2.5.0 hace falta
  esa resiembra. La 2.5.1 cambia además la forma de la huella: si sembraste con la 2.5.0,
  resiembra una vez (`make -C platform reseed` y `make -C platform pipeline REINICIAR=1`). A partir de la
  2.5.1, ajustar una alerta no obliga a resembrar. La 2.5.2 cambia texto de las acciones
  (`nota_docente`), que sí está en la huella: si sembraste con la 2.5.1, resiembra.
- **Reubicaciones del hotel** (supuesto S15, 2.3.0): las cancelaciones cuyo motivo empieza por
  «Reubicación» son del hotel, no del cliente. La reserva deja de ser neta, pero no cuenta en
  las tasas de cancelación, el ingreso cancelado, las penalizaciones ni la reventa.
- **Repetición por titulares** (2.3.0): los huéspedes con estancia y los repetidores son los
  titulares de las reservas (`reservation.guest_id`), no los acompañantes.
- **Reventa con demanda desplazada** (supuesto S17, 2.3.0): una venta posterior a una
  cancelación del cliente solo cuenta como reventa en las noches en que ese tipo de habitación
  del hotel acabó lleno; si sobraban habitaciones, la venta no se debe a la cancelación y el
  ingreso cancelado se considera perdido (`ingreso_reventa`, `ingreso_perdido_neto`).
- **Mercado de Austria** (supuesto S16, 2.3.0): los residentes en Austria van con el mercado
  alemán; la comparación con el ISTAC lo tiene en cuenta.
- **Línea base** (supuesto S10): calculada en el almacén con los datos de 2024 a escala 1 y la
  semilla por defecto (`atlantida-dbt linea-base`): la de O1, O2 y O3 en la 2.3.0 y la de O4 en
  la 2.4.1, con el modelo de IA oficial y los parámetros del semáforo ya fijados.
- **Semáforo de aspectos** (2.4.0): los `parametros` de la métrica base `dias_aspecto_en_rojo`
  (`ventana_dias`, `umbral`, `menciones_min`, `hueco_max_dias`, `modelo` y `version_modelo`)
  son la única fuente del cálculo: `atlantida-dbt generar` los lleva a dbt (macro
  `parametros_metricas` y semilla `def_parametro`) y las pruebas del simulador los leen con
  `parametros_rojo()`. Un día sin muestra suficiente conserva el estado como mucho
  `hueco_max_dias` días; solo cuentan las clasificaciones del modelo de IA oficial (el almacén
  toma su nombre de la ficha oficial de `meta.modelo_ia`) hechas sobre el texto actual de la
  reseña. Cambiar un parámetro cambia la huella de versión del KPI `dias_max_aspecto_en_rojo`.

## Interfaces para el simulador y las fuentes

Lo que el simulador y los descargadores deben leer de aquí o hacer cierto en los datos:

- **Hoteles**: `hoteles` (código, isla, municipio, tipo, estrellas, habitaciones).
- **Horizonte**: `horizonte_simulado` = `SIM_START`/`SIM_END` de `platform/.env.example`
  (2023-01-01 → 2026-03-31; un test comprueba que coinciden).
- **Historia de huéspedes**: `horizonte_simulado.historia_huespedes_desde` = 2022-01-01
  (`SIM_HISTORIA_DESDE` en `platform/.env.example`; el validador exige que sea como tarde el
  1 de enero de `periodo_base − 2`). Entre esa fecha y `SIM_START` el simulador genera solo estancias
  de huéspedes (reservas `checked_out` con su `reservation_guest` y `guest`), sin el resto de
  la operación; desde `SIM_START`, el PMS completo.
- **Importes**: `stay_night.room_revenue` y `reservation.total_amount` son solo alojamiento,
  netos de IGIC, con el paquete repartido según `desagregacion_regimen`; el resto del paquete
  se registra en `folio_charge` (`department = fnb`, `service_date` = cada noche).
  `total_amount` = suma del `room_revenue` de la estancia (en la divisa del contrato).
- **Cobro**: las reservas OTA se garantizan con tarjeta y se cobran a la llegada (también las
  no reembolsables); desde que una fila `rate_restriction` (`deposito_obligatorio`,
  `parametro` = 60) está vigente en un hotel y canal, las reservas con más antelación pagan al
  reservar un depósito (`payment_type = deposit`) del `rate_plan.deposit_pct` de su tarifa,
  que se retiene si cancelan (`cancellation.penalty_amount`).
- **Programa de fidelización**: el día 1 de cada mes desde `A3.inicio`, es elegible la ficha
  `guest` titular de una estancia `checked_out` con salida en los 730 días anteriores; el
  programa da de alta automáticamente a los elegibles nuevos identificables (con `document_id`
  o con un correo propio, no el alias enmascarado de una OTA) que aceptan las comunicaciones,
  un 30-40 % de los elegibles (`loyalty_member.enrolled_at` = ese día 1 a las 06:00); `left_at`
  queda nulo (nadie se da de baja en el horizonte). El grupo de comparación de A3 son los
  elegibles identificables sin alta; el PMS no lo registra porque no es un hecho operativo.
- **Calendario de acciones**: `acciones[].inicio`, `fin`, `hoteles_piloto`,
  `hoteles_control` y `regla_pms` (las filas de `rate_restriction` y `guest_flag` que se
  escriben y desde cuándo); campaña A2 en `campaign`/`campaign_hotel` del 2025-06-01 al
  2025-08-31 sin YAI.
- **Vocabulario**: `contrato_pms.yml` → `restricciones` (`guest_flag.flag`,
  `rate_restriction.rule`) y la columna `rate_restriction.parametro`.
- **Fuentes externas**: columnas exactas de `contrato_externo.yml`.
- Los hechos de negocio que el simulador debe hacer ciertos para que los textos de la
  definición sean coherentes están documentados en el material del profesor (no publicado).

## Validación

```bash
uv run pytest platform/definicion -q
```

Cualquier cambio en `atlantida.yml` o `contrato_pms.yml` debe pasar estas pruebas (y la
CI las ejecuta en cada *pull request*).
