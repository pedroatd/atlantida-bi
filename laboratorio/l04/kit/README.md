# Kit del laboratorio L4: modelo dimensional de tu proyecto con dbt

Con este kit construyes con dbt el modelo dimensional de tu proyecto sobre la carga en crudo
del L3: *staging* sobre `raw` con los datos personales seudonimizados, la historia SCD2 con
*snapshots* y, en `marts`, tus dimensiones (con su clave sustituta y su miembro desconocido) y
tus hechos (con su grano). Todo vive en la misma base `proyecto` del kit del L3.

El kit **no trae la solución de tu proyecto**: las plantillas de `models/` llevan huecos
(`hueco(…)` y `-- COMPLETA:`) que completas tú, y `make comprobar` mira en la base si tu modelo
cumple lo que declaras en `modelo.yml`.

El zip se descomprime en una carpeta `l04-kit/`. Déjala **junto a `l03-kit/`** (el kit busca
la conexión en `../l03-kit/.env`) y entra en ella (`cd l04-kit`) para todas las órdenes. Si tu
kit del L3 está en otro sitio, añade `L3_KIT=ruta/al/l03-kit` a cada orden.

## Requisitos

- El kit del L3 con tu base levantada (`make base` en `l03-kit`) y tu carga hecha (`make cargar`).
- [`uv`](https://docs.astral.sh/uv/) (instala Python 3.12, dbt y las demás dependencias exactas
  de `uv.lock`; la primera ejecución las descarga, así que necesitas red) y `make`.

## Pasos

1. `make sal` genera en `.env` la sal de los seudónimos, al azar y sin mostrarla. Hazlo una sola
   vez: si la cambias, cambian todos los seudónimos. Nunca subas `.env` a un repositorio.
2. `make fuentes` lee tu `contrato.yml` del L3 y escribe `models/staging/_fuentes.yml`: la fuente
   `raw`, con tus tablas, sus columnas y las pruebas de su clave según la disposición. Marca las
   columnas de `personales` y avisa, con tabla y columna, de lo que el contrato declara y `raw`
   no tiene. Vuelve a ejecutarlo si cambias el contrato.
3. Diseña el modelo: la matriz bus (procesos × dimensiones), el grano de cada hecho y, por
   atributo, si un cambio se sobrescribe (SCD1) o guarda historia (SCD2).
4. Copia las plantillas y complétalas: `models/staging/plantilla_stg.sql` (una vista por tabla
   de `raw`, con `seudonimo('columna')` en cada dato personal), `models/marts/plantilla_dim.sql`
   y `models/marts/plantilla_fct.sql`. Quita la llamada a `hueco(…)` al completar cada una y
   borra las plantillas que no uses: mientras sigan, `make dbt` dice qué falta en cada una.
5. Si una dimensión guarda historia, completa `snapshots/plantilla.yml` y ejecuta `make snapshot`
   después de cada carga del L3: solo ve los cambios entre dos ejecuciones. Ver «La historia
   SCD2».
6. `make dbt` ejecuta `dbt build` (modelos, *snapshots* y pruebas); `make dbt ARGS="run -s
   dim_cliente"` ejecuta otra orden de dbt.
7. Declara tu modelo en `modelo.yml` (ver «Lo que comprueba `make comprobar`») y ejecuta
   `make comprobar`.

Otras órdenes: `make docs` (genera la documentación de dbt y la sirve en
<http://127.0.0.1:8080>; `PUERTO=8081` si está ocupado; se sale con Ctrl+C). `make` sin nada
las lista. Para mirar el resultado a mano, `make psql` en el kit del L3 y, dentro, `\dt marts.*`.

## La historia SCD2

- **La primera versión.** Con `strategy: timestamp`, el *snapshot* abre la primera versión de
  cada clave en su última modificación (`updated_at`), que suele ser posterior a los hechos más
  antiguos: un hecho anterior no casaría con ninguna versión e iría al −1. Haz que la primera
  versión de cada clave cubra los hechos más antiguos. `make comprobar` avisa si muchas filas
  de un hecho van al desconocido.
- **Ver una segunda versión.** Hace falta que cambie en el origen una fila de **la tabla de la
  dimensión**, no solo los hechos. Si la dimensión sale de un CSV, edita en `datos/` del kit del
  L3 unas filas (el atributo SCD2 y, con `strategy: timestamp`, también su columna de última
  modificación, con un instante posterior); si sale de la base de origen, un `update` en un
  `.sql` propio aplicado con `make -C ../l03-kit origen F="$PWD/mis_cambios.sql"`. Después,
  `make -C ../l03-kit cargar`, `make snapshot` y `make dbt`. El SQL de cambios del proyecto de
  ejemplo (`prestamos_cambios.sql`) solo cambia filas de hechos: no da historia a ninguna
  dimensión.
- **Los borrados.** Con `disposicion: merge`, una fila borrada en el origen sigue en `raw` (el
  comprobador del L3 lo avisa) y, por tanto, en tus hechos. Decide si te importa y dilo en tu
  nota (o usa `replace` en el L3).
- **Los tipos.** Da en *staging* un solo tipo a cada clave (un CSV la deja como texto y la base
  de origen como `bigint`) y pasa los instantes a UTC sin zona (`actualizado at time zone
  'UTC'`), el tipo de `dbt_valid_from`; si no, dbt avisa en cada *snapshot* de «Data type of
  snapshot table timestamp columns (DATETIME) doesn't match derived column 'updated_at'
  (DATETIMETZ)».

## Esquemas

| Esquema | Qué guarda |
|---|---|
| `raw` | Tu carga del L3, sin tocar: la única capa con datos personales en claro. |
| `staging` | Vistas sobre `raw`: nombres y tipos claros, personales seudonimizados. |
| `snapshots` | La historia SCD2 (`dbt_valid_from`, `dbt_valid_to`). |
| `marts` | Dimensiones y hechos. |

## Los seudónimos

`seudonimo(expr)` (en `macros/seudonimo.sql`) calcula el SHA-256 de la sal y el valor como
texto: el mismo valor da siempre el mismo seudónimo, así que se puede unir y contar sin ver el
dato. No es anónimo: sigue siendo dato personal (RGPD, art. 4.5). La sal no se escribe en el
SQL: el `Makefile` la pone en la conexión (`PGOPTIONS`), y por eso dbt se ejecuta siempre con
`make`. Un `dbt` lanzado a mano se detiene en *staging* con «Falta la sal de los seudónimos».

Un dato con pocos valores posibles (una fecha, un código postal) se recupera por fuerza bruta
si se conoce la sal: `make fuentes` avisa de los que no son texto. A veces es mejor
generalizarlo (solo el año, una zona) que seudonimizarlo.

## Lo que comprueba `make comprobar`

En `modelo.yml` declaras tus hechos (con su grano y sus claves foráneas), tus dimensiones (con
su clave sustituta) y, en las SCD2, su clave natural, sus columnas de validez y la tabla del
contrato de la que sale su historia. El contrato del L3 aporta las `personales`. Cada mensaje
dice la tabla y la columna:

- el grano de cada hecho es único y sus columnas no tienen nulos;
- sus claves foráneas son enteras y no tienen huérfanos ni nulos (lo que no casa va al
  desconocido, −1); hacia una SCD2 con `fecha` (la columna del hecho que elige la versión),
  cada fila apunta a la versión vigente en esa fecha, no a la actual;
- cada dimensión tiene su clave sustituta entera y única y su miembro desconocido (−1); en una
  de tipo 1 con `clave_natural`, esta no se repite;
- en una SCD2, cada clave natural tiene exactamente una versión vigente (`hasta` nulo o del año
  9999), todas tienen `desde`, ningún intervalo `[desde, hasta)` está vacío o invertido y los de
  una misma clave no se solapan; avisa de los huecos entre versiones y, si su tabla no tiene
  columna de última modificación y su *snapshot* usa `strategy: timestamp`, de que necesita
  `strategy: check`;
- busca columnas de `personales` en claro fuera de `raw` (en *staging*, en los *snapshots* y
  en `marts`): una con el mismo nombre que comparta valores con la de `raw`; cualquiera que,
  en una tabla que conserve la clave de `raw` con su nombre, tenga el mismo valor en la misma
  fila; y, si el dato es casi único por persona (un correo, un nombre), cualquiera con muchos
  de sus valores. Es una heurística, no una garantía: no ve un dato transformado (en
  mayúsculas, recortado, concatenado) ni uno con pocos valores (un distrito, una fecha)
  renombrado y sin la clave. Que no salga nada no te exime de revisar tus modelos. Un dato
  personal del contrato que no está en `raw` sale como error: no se ha podido comprobar.

No mira cifras: un modelo correcto pasa con cualquier volumen de datos y aunque aún no haya
historia (con una sola carga, cada clave tiene una sola versión). Solo avisa, sin fallar y con la
proporción, si más del 5 % de las filas de un hecho van al desconocido (−1) de una dimensión:
suele ser una unión que no casa (la primera versión de una SCD2 que empieza tarde, una clave de
otro tipo).

El −1 es «debería existir, pero no se ha encontrado». Lo que no corresponde por diseño no es un
desconocido: la fecha de fin de algo que aún no ha terminado, un rol de fecha opcional.
Déjalo nulo y declara la clave `opcional: true` con su `motivo` (los nulos dejan de ser error;
el aviso del −1 sigue), o apúntalo a un miembro −2 «no aplica» si la dimensión tiene esa fila.
Un calendario generado completo no necesita el −1: declara `miembro_desconocido: false` con su
`motivo`, y entonces ningún hecho puede apuntarle con −1:

```yaml
hechos:
  fct_mi_proceso:
    grano: [mi_id]
    claves_foraneas:
      mi_entidad_sk: {dimension: dim_mi_entidad, fecha: mi_instante}  # la vigente en mi_instante
      mi_fecha_fin_sk:
        dimension: dim_fecha
        opcional: true
        motivo: lo que aún no ha terminado no tiene fecha de fin
dimensiones:
  dim_fecha:
    clave_sustituta: fecha_sk
    miembro_desconocido: false
    motivo: calendario generado completo
```

Con `strategy: check`, el *snapshot* no sabe cuándo cambió la fila: abre la versión nueva en el
instante en que se ejecuta. Los hechos entre el cambio real y ese *snapshot* toman la versión
anterior. Si la usas, dilo en tu nota.

## Si algo falla

| Mensaje | Causa | Arreglo |
|---|---|---|
| «no encuentro ../l03-kit/.env» | El kit del L3 no está al lado. | `L3_KIT=ruta` en cada orden. |
| «completa models/…: …» | Esa plantilla sigue sin completar. | Complétala o bórrala si no la usas. |
| «depends on a source named 'raw.…' which was not found» | Falta `make fuentes`, o la tabla no está en tu contrato. | `make fuentes`. |
| «Falta la sal de los seudónimos» | dbt lanzado a mano. | `make dbt`. |
| Una conexión rechazada | La base del L3 no está levantada. | `make base` en el kit del L3. |
| «There are 1 unused configuration paths: - snapshots.proyecto» | Aún no hay ningún *snapshot*. | Desaparece al definir el primero. |
| «No such option: --full-refresh» en `make snapshot` | Un *snapshot* no se reconstruye así. | En `make psql` del kit del L3, `drop table snapshots.snp_<tabla>;` y otra vez `make snapshot` (pierdes su historia). |
| `make dbt ARGS="ls … --output json"` da una línea enorme | Es el formato de dbt. | Las columnas de `raw` están en `models/staging/_fuentes.yml`. |
| `ERROR …: el grano (…) se repite` | Falta una columna en el grano, o un `join` multiplica filas. | Revisa el grano de tu nota y las uniones del hecho. |
| `ERROR …: N filas sin su fila en dim_…` (huérfanas) | La clave no está en la dimensión. | Lo que no casa va a `-1` (`coalesce(…, -1)`). |
| `ERROR …: N filas con la clave nula` | Un `left join` sin `coalesce`. | `-1`; o `opcional: true` si falta por diseño. |
| `ERROR dim_…: falta el miembro desconocido` | La dimensión no tiene la fila `-1`. | Añádela; o `miembro_desconocido: false` si no la necesita. |
| `ERROR …: la clave sustituta es de tipo text` | Un hash sin convertir. | Conviértelo a entero (`bigint`). |
| `ERROR …: más de una versión vigente` o `sin ninguna versión vigente` | Intervalos mal calculados. | Una sola versión por clave con `hasta` nulo o de 9999. |
| `ERROR …: intervalos … que se solapan` o `vacío o invertido` | `desde` y `hasta` mal encadenados. | El `hasta` de una versión es el `desde` de la siguiente. |
| `ERROR …: N filas apuntan a una versión … que no estaba vigente` | El hecho se une por la versión actual. | Une por el intervalo: `desde <= fecha` y `fecha < hasta`. |
| `AVISO …: el N % de las filas van al desconocido` | La primera versión empieza tarde, o una clave de otro tipo. | Lee la pista del aviso. |
| `AVISO …: con huecos entre versiones` | Una versión empieza después de que acabe la anterior. | Encadena los intervalos. |
| `ERROR …: dato personal … en claro fuera de raw` | Una `personal` sin `seudonimo()`. | Seudonimízala en *staging* o no la uses. |
