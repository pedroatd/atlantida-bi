# atlantida-el: las cargas

**EL** significa *extract and load* (extraer y cargar): copiar los datos tal cual de su origen a la
capa `raw` del DWH. La transformación (la «T» de ELT) la hace dbt después; está explicada en
`platform/dbt/README.md`. Las cargas usan **dlt**, una librería de Python para mover datos.

Todo se ejecuta dentro del contenedor `elt` (el `Makefile` se encarga), así que no necesitas
instalar nada más que lo del README de la raíz.

## Dónde quedan los datos

| Esquema o tabla | Contenido |
|---|---|
| `raw_pms` | Las 21 tablas del PMS con sus nombres originales (en inglés), más dos columnas: `_loaded_at` (cuándo se cargó la fila) y `_origen` (de dónde vino). |
| `raw_ext` | Las fuentes externas (tiempo, festivos, llegadas, tipos de cambio y el rate shopper). Los valores del rate shopper se guardan **como texto**, tal como llegan. |
| `meta.carga` | Una fila por tabla y ejecución: cuándo empezó y acabó, cuántas filas, estado (`en_curso`, `ok`, `error` o `instantanea`) y un campo `detalle`. |

Para mirar el registro de cargas:

```bash
make -C platform psql-dwh
```
```sql
select * from meta.carga order by id desc limit 30;
```

o, desde `platform/`, el resumen de las últimas cargas con `make el-estado` (no hace falta
ejecutar antes `make el`).

## Con qué usuario se lee el PMS

Las cargas no leen el PMS con su propietario sino con `pms_el`, un rol de **solo lectura**
(principio de mínimo privilegio). Puede leer todas las tablas de `public` y, del esquema interno
del simulador, solo `sim.reloj`; no puede escribir ni leer el resto de `sim`. Sus claves son
`PMS_EL_USER` y `PMS_EL_PASSWORD` en `.env`; `make up`, `make seed` y `make reseed` lo crean o
lo actualizan (también `make roles-pms`, que es idempotente). Si dejas `PMS_EL_USER` vacío, las
cargas vuelven a usar el propietario del PMS (`PMS_USER`).

Las cargas también se pueden lanzar desde Dagster, que añade planificaciones, comprobaciones de
calidad y linaje: mira `platform/orchestration/README.md`.

## Cómo se ejecuta

Desde `platform/` (o con `make -C platform …` desde la raíz):

| Orden | Qué hace |
|---|---|
| `make el` | Carga incremental: solo lo nuevo o cambiado. |
| `make el REINICIAR=1` | Vuelve a cargar todo desde cero: **borra** lo cargado en `raw_pms` y `raw_ext` y el estado incremental, y lo vuelve a leer entero. |
| `make el ORIGEN=api` | Carga desde la API de cambios del profesor en lugar del PMS local. |
| `make el SOLO=externas` | Solo las fuentes externas (`SOLO=pms`: solo el PMS). |
| `make pipeline` | Carga incremental y construcción del almacén con dbt, en un solo paso. |

Fuera de Docker también puedes usar `uv run atlantida-el cargar` desde la raíz del repositorio:
la orden lee `platform/.env` (como `atlantida-sim` y `atlantida-dbt`, sin pisar las variables que
ya tengas definidas) y usa los puertos publicados allí. `make pipeline`, igual que `make el`,
acepta `ORIGEN=api`.

En la salida solo verás los errores de dlt, la herramienta que carga los datos: sus avisos internos
(en inglés) no indican un fallo. Para verlos, define `RUNTIME__LOG_LEVEL=WARNING`. Los avisos
propios (por ejemplo, que el rate shopper no ha respondido) empiezan por `AVISO` y `make pipeline`
los repite al final. El código de salida es 3 si hay que volver a cargar desde cero (cambio de
origen o PMS del profesor resembrado), 1 en cualquier otro error.

### Cuánto tarda

Medido a escala 1 (la cadena completa) en un equipo de sobremesa (12 hilos, 47 GB de RAM, WSL2):

| Paso | Tiempo |
|---|---|
| `make seed` (sembrar el PMS) | unos 6 minutos |
| `make pipeline`, primera vez | unos 12,5 minutos: unos 10 de cargas (EL) y unos 2,5 de `dbt build` |
| `make pipeline`, repetido sin cambios en el PMS | unos 3 minutos: unos 20 segundos de cargas; el resto es `dbt build` |

Estas cifras se midieron cuando `make pipeline` aún no clasificaba las reseñas ni aplicaba los
paneles. Hoy, con todo, la primera vez tarda unos 25 minutos y una carga incremental unos 4,5
(medida mientras se navegaba por los paneles); el detalle está en el README raíz.
| `make historico` (`PASO=mes`) | unos 30 minutos |

Memoria (suma de los contenedores según `docker stats`): hasta unos 6 GB durante la primera carga y
el `dbt build` (el DWH unos 4,5 GB, contando la caché de PostgreSQL, que el sistema libera si
falta memoria; el contenedor `elt`, menos de 1 GB) y unos 8 GB durante `make historico`. Disco: el
DWH ocupa unos 5,6 GB y el PMS unos 2,2 GB. A escala 0,02, la primera ejecución de `make pipeline`
tarda unos 7,5 minutos y las repeticiones unos 46 segundos. A escala reducida casi todo ese tiempo
es la carga de las tarifas de mercado, que no depende de la escala: `RS_TARIFAS_DESDE` en `.env`
acorta la primera carga. Son cifras orientativas: dependen de
tu equipo.

## Carga incremental

Cada tabla se lee desde el último `updated_at` cargado (dlt guarda ese valor en el propio DWH, en
`raw_pms._dlt_pipeline_state`). Las filas nuevas se insertan y las que cambiaron sustituyen a la
anterior (*merge* por la clave primaria). Por eso repetir una carga **no duplica nada**: la segunda
vez, las tablas con *merge* traen cero filas si el PMS no ha cambiado. Con la simulación viva en
marcha tampoco se pierden cambios: la próxima carga continúa desde donde terminó la anterior.

Una tabla cuya clave admite valores nulos (`rate_restriction`) no se puede combinar por clave y se
vuelve a leer entera en cada carga.

Después de `make reseed`, las fechas `updated_at` del PMS son las de la simulación, no las del
momento de sembrar: si la resiembra cambia los datos (otra escala, semilla o patrones), la carga
incremental no los ve como nuevos. En ese caso, carga desde cero: `make pipeline REINICIAR=1`.
Si solo cambió la huella (por ejemplo, una versión nueva de `atlantida.yml`) con los mismos datos,
basta `make pipeline`.

## Cargar desde la API del profesor

El profesor puede publicar los cambios de su PMS mediante una API protegida con un token. Para
cargar desde ella, en `platform/.env`:

```
ORIGEN_PMS=api
SIM_API_URL=https://…/v1
SIM_API_TOKEN=…
RS_URL=https://…/rs
RS_TOKEN=
```

(las URL y el token te los da el profesor; `RS_TOKEN` vacía usa el de la API). Ten en cuenta:

- Dentro del contenedor `elt`, `localhost` es **el propio contenedor**, no tu equipo. Si la API
  corre en tu equipo, usa el nombre de su servicio (`http://simulator-api:8002/v1`) o la IP del
  anfitrión.
- Cada carga fija al empezar un **corte** (el reloj de la API) y lee hasta él: ninguna página trae
  cambios posteriores al corte aunque el profesor tenga en marcha el modo vivo del simulador (el que sigue generando reservas y cambios en tiempo real; véase `platform/simulator/README.md`).
- La primera vez, ejecuta `make el REINICIAR=1`. Si antes cargaste el PMS local, los dos orígenes no
  se mezclan: cambiar de origen exige reiniciar.
- Si el profesor vuelve a sembrar su PMS, la carga se detiene con un mensaje (código de salida 3)
  y debes repetirla desde cero con `make el SOLO=pms REINICIAR=1` (solo el PMS, sin volver a pedir
  las fuentes externas; desde la raíz del repositorio, `make -C platform el SOLO=pms REINICIAR=1`).
- Hay dos ediciones de la plataforma: en la completa, las tarifas de mercado salen del rate
  shopper local con los datos de tu siembra (`make seed`); en la del alumnado, del rate shopper
  del profesor (`RS_URL`). Sin `RS_URL` no se intenta conectar: las demás fuentes externas se
  cargan, `compset_diario` y `rate_shopper` quedan con error en `meta.carga` y `make pipeline`
  lo indica con un `AVISO` que dice qué pedir al profesor.
- Si el rate shopper responde 401 o 403, el token no es válido: la carga lo anota sin reintentar
  (revisa `RS_TOKEN` o `SIM_API_TOKEN`).

## Fuentes externas y rate shopper

Las fuentes externas son instantáneas versionadas (ver `platform/sources/README.md`) que se vuelven
a cargar enteras. El rate shopper es un proveedor externo: puede no estar disponible o enviar datos
imperfectos. Si falla, la carga continúa con el resto, repasa los últimos días en la siguiente
ejecución y deja en `meta.carga` (campo `detalle`) lo que observó. Esos datos se guardan tal como
llegan; descubrir qué ocurre con ellos es parte del curso.

## Replicación lógica del PMS (`wal_level=logical`)

El PMS arranca con `wal_level=logical`, necesario para la captura de cambios (CDC) que verás en el
curso. Si vienes de una versión anterior, `make up` **recrea** el contenedor `pms-db` con ese
ajuste y **conserva el volumen**: tus datos siguen ahí.

## Errores frecuentes

| Mensaje | Qué hacer |
|---|---|
| «El PMS no tiene las tablas del contrato» | `make seed` (el PMS aún no está sembrado). |
| «No se puede conectar con el DWH (¿has ejecutado make up?)» | El servicio no responde: `make up` (y comprueba `DWH_PORT`). |
| «el DWH rechazó el usuario o la contraseña» | La clave de `.env` no es la del rol: revisa `LOADER_PASSWORD` o aplica la nueva con `make migrar`. |
| «El DWH no tiene los esquemas de esta versión» | `make migrar`. |
| «raw_pms se cargó desde el origen…» | Cambiaste de origen: `make el REINICIAR=1`. |
| «La API de cambios rechaza el token» | Revisa `SIM_API_TOKEN` en `.env`. |
| «Falta SIM_API_TOKEN» | Pon en `.env` el token que te da el profesor. |
| «No se puede conectar con la API de cambios» | Revisa `SIM_API_URL`, que el nombre resuelva (DNS) y el certificado; si todo está bien, pregunta al profesor. |
| «El servidor del profesor no está disponible» | Su API no responde (HTTP 502, 503 o 504): inténtalo en unos minutos o pregunta al profesor. |

## Airbyte (perfil `full`)

Alternativa a dlt para quien tenga recursos de sobra: ver `airbyte/README.md`.
