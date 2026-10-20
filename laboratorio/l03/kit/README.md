# Kit del laboratorio L3: carga en crudo de tu proyecto

Con este kit montas una base de datos nueva para tu proyecto y escribes su carga en crudo: tus
ficheros originales (CSV) y tu base operacional (tus datos sintéticos) acaban en el esquema `raw`
de la base `proyecto`, con dlt, sin transformar. Cada fila lleva `_loaded_at` (cuándo se cargó) y
`_origen` (de dónde vino), y cada tabla deja una fila por ejecución en `meta.carga`.

El kit **no trae la solución de tu proyecto**: `carga.py` tiene dos funciones marcadas como
`HUECO` que completas tú, y `make comprobar` te dice si tu carga cumple el contrato.

El zip se descomprime en una carpeta `l03-kit/`: entra en ella (`cd l03-kit`) para todas las
órdenes.

## Requisitos

- Docker (con `docker compose`).
- [`uv`](https://docs.astral.sh/uv/) (instala Python 3.12 y las dependencias exactas de `uv.lock`;
  la primera ejecución las descarga, así que necesitas red).
- `make` y `openssl` (si falta `openssl`, el kit usa Python para generar la contraseña).

En Windows, trabaja dentro de WSL2 (Ubuntu):

- Docker Desktop con la integración de WSL activada para tu distribución, o Docker Engine
  instalado dentro de WSL;
- `sudo apt install make` (Ubuntu en WSL no lo trae);
- uv: `curl -LsSf https://astral.sh/uv/install.sh | sh`;
- guarda el kit en tu carpeta de Linux (`~/…`), no en `/mnt/c/…`: ahí `chmod 600 .env` no tiene
  efecto y todo va más lento.

## Pasos

1. `make base`: crea `.env` (con una contraseña aleatoria que no se muestra) y la carpeta `datos/`,
   y levanta un PostgreSQL en `127.0.0.1:5440` con dos bases: `proyecto_origen` (tu «sistema
   operacional») y `proyecto` (el destino, con los esquemas `raw` y `meta`). Si quieres cambiar
   el puerto o el nombre del proyecto de Docker antes de levantarla, copia `.env.ejemplo` a `.env`,
   edítalo y después ejecuta `make base` (la contraseña se genera igual).
2. Copia tus ficheros originales (CSV) a `datos/` y míralos: `head -n 3 datos/*.csv` y
   `file datos/*.csv` (debe decir `UTF-8` o `ASCII`; `ISO-8859` o `Non-ISO extended-ASCII` es
   Latin-1 o Windows-1252). El zip no trae `datos/` porque tus datos nunca van al repositorio.
3. `make origen F=mis_datos.sql` restaura tus datos sintéticos en `proyecto_origen` (un `.dump`
   de `pg_dump -Fc` también vale: `make origen F=copia.dump`). Ver «Restaurar tu SQL».
4. Escribe `contrato.yml` (ver «El contrato»). `make columnas` enseña cómo quedarán en `raw` los
   nombres de las cabeceras de tus CSV, y `make contrato` lo valida y lee tus ficheros.
5. Completa los huecos de `carga.py` (`recursos_de_ficheros` y `recursos_de_origen`). Su
   documentación dice qué API de dlt usar; las decisiones van en el contrato y en tu nota.
   `carga.py` solo llama al hueco de origen si el contrato tiene tablas sin `fichero`: para probar
   primero los ficheros, comenta (con `#`) las tablas de origen del contrato.
6. `make cargar` ejecuta tu carga una vez.
7. `make comprobar` ejecuta tu carga dos veces y comprueba la idempotencia (la segunda ejecución
   no duplica ni reescribe y, en las tablas incrementales, no lee nada), el esquema (tablas que ha
   cargado dlt, columnas, claves, linaje), el registro de `meta.carga` y que `raw` coincide con
   el origen (tus tablas de `proyecto_origen` y tus ficheros). Anota también cuántas filas leyó
   cada ejecución (líneas `INFO`).

Otras órdenes: `make psql` (consola SQL del destino; `make psql BASE=proyecto_origen` para el
origen; se sale con `\q`), `make recargar T=tabla` (borra esa tabla de `raw` y su cursor y la
carga desde cero), `make descartar` (descarta una carga fallida que dlt reintenta, ver «Si algo
falla»), `make parar` (detiene la base y conserva los datos) y `make borrar` (borra la base, sus
datos y el estado de dlt; pide confirmación, o `make borrar SI=1`). `make` sin nada las lista.

Para mirar el resultado a mano: `make psql` y, dentro, `\dt raw.*`, `\d raw.tu_tabla` o
`select tabla, inicio, filas, estado from meta.carga order by id desc limit 10;`.

Nunca subas `.env`, `datos/` ni `.dlt-estado/` a un repositorio (`.gitignore` ya los excluye).

## El contrato

Una entrada por tabla de `raw` (la plantilla trae una de fichero y otra de origen):

| Campo | Qué es |
|---|---|
| `columnas` | Las columnas que debe tener, con el nombre que deja dlt. Sin las de linaje (`_loaded_at`, `_origen`, `_fila`) ni las de dlt (`_dlt_*`): el comprobador las mira aparte. |
| `clave` | Las columnas que identifican una fila. |
| `disposicion` | `merge`, `replace` o `append`. Con `merge`, la clave no admite repetidos ni nulos; con `replace`, admite nulos y `raw` debe tener las mismas filas que el origen; con `append`, cada clave puede tener varias versiones y lo único es la clave con la columna incremental. `replace` no lleva `incremental`. |
| `incremental` | Opcional: la columna de última modificación. |
| `fichero` | Opcional: el CSV dentro de `datos/`, una lista de ellos o un patrón (`ventas_*.csv`). Sin él, la tabla sale de `proyecto_origen`. |
| `esquema_origen` | Opcional: el esquema de la tabla en `proyecto_origen` (por omisión, `public`). |
| `personales` | Opcional: las columnas con datos personales, para seudonimizarlas en *staging* (L4). |
| `separador`, `codificacion` | Opcionales, solo con `fichero`: `","`, `";"`, `"\t"` o `"\|"`, y la codificación si no es UTF-8 (`cp1252`, `latin-1`). |

## Nombres de columna

dlt normaliza cada cabecera: minúsculas, espacios y signos a `_`, y las letras que no son ASCII
(tildes, `ñ`) también pasan a `_`; un signo al final queda como `x` y un número al principio
recibe un `_` delante. Por ejemplo:

| Cabecera | En `raw` |
|---|---|
| `Fecha Alta` | `fecha_alta` |
| `Año` | `a_o` |
| `Código Cliente` | `c_digo_cliente` |
| `Nº socio` | `n_socio` |
| `Importe (€)` | `importex` |
| `% IVA` | `_iva` |

`make columnas` (o `make columnas F=datos/ventas.csv`) lo enseña antes de cargar y avisa si dos
cabeceras quedan con el mismo nombre. Escribe en el contrato el nombre que queda; no renombres
las columnas en `carga.py` (eso ya es transformar).

## Si tu proyecto…

- **…tiene varios ficheros para una tabla** (`ventas_2031_01.csv`, `ventas_2031_02.csv`…): pon
  una lista o un patrón en `fichero`. Se cargan todos, cada fila con su `_origen`
  (`fichero:ventas_2031_01.csv`) y su `_fila`.
- **…tiene un fichero sin clave natural** (lecturas, filas idénticas repetidas): usa
  `clave: [_origen, _fila]` (el fichero y la línea) con `disposicion: replace`, y explica en la
  nota que esa clave no sobrevive a un fichero reordenado.
- **…tiene CSV con números o fechas «a la española»** (`12,50`, `18/10/2031`): en `raw` quedan
  como texto, tal cual; los tipos se ponen en *staging*. No declares `incremental` sobre una fecha
  en texto que no sea ISO (`aaaa-mm-dd`): dlt compara el texto y el orden no es el de las fechas
  (`make contrato` lo avisa). dlt sí detecta los instantes ISO y los guarda como `timestamp`.
- **…tiene un cursor con nulos** (`actualizado` vacío en filas que nunca se modificaron): dlt
  falla salvo que elijas `on_cursor_value_missing` en `dlt.sources.incremental`; `make comprobar`
  cuenta esos nulos en el origen.
- **…borra filas en el origen**: `merge` no propaga los borrados (el comprobador da un aviso con
  cuántas claves de `raw` ya no están en el origen) y `replace` sí. Decide qué necesitas.

## Restaurar tu SQL

`make origen` restaura en una sola transacción (si falla, no queda nada a medias) y sin los
dueños ni los permisos del equipo donde se hizo la copia (quita las líneas `ALTER … OWNER TO`,
`GRANT` y `REVOKE` de un `.sql`, y usa `--no-owner --no-privileges` con un `.dump`). Un `.dump`
se puede restaurar más de una vez (`--clean --if-exists`); un `.sql` solo si está escrito para
eso. Si sacas el SQL de otra base con `pg_dump`, usa `pg_dump --no-owner --no-privileges`. El SQL
debe ser de PostgreSQL: un volcado de MySQL o SQLite (comillas invertidas, `AUTO_INCREMENT`) no
vale.

## El estado de dlt

dlt guarda su estado (los cursores incrementales) en `.dlt-estado/` y también en
`raw._dlt_pipeline_state`. Si borras solo `.dlt-estado/`, dlt lo recupera de la base y el cursor
sigue donde estaba; si borras solo la base, el estado local cree que ya cargó todo. Para empezar
de cero, `make borrar` y `make base`; para reiniciar una tabla (por ejemplo, porque has cambiado
su cursor), `make recargar T=tabla`.

## Si algo falla

- `completa «recursos_de_ficheros» en carga.py`: todavía no has completado ese hueco.
- `falta la variable PROYECTO_CLAVE`: ejecuta `make base`, que crea `.env`.
- `alguna tabla del contrato sin «fichero» no está en proyecto_origen`: revisa el nombre (y
  `esquema_origen`) en `contrato.yml` o restaura tus datos con `make origen`.
- `no hay ningún fichero … en datos/`: falta ese fichero (o el patrón no encuentra ninguno).
- `… no está en utf-8`: vuelve a exportarlo como «CSV UTF-8» (en Excel en español, «CSV
  (delimitado por comas)» guarda en Windows-1252), conviértelo
  (`iconv -f cp1252 -t utf-8 ventas.csv > ventas-utf8.csv`) o declara `codificacion: cp1252`.
- `…, línea N: M campos y la cabecera tiene K`: esa fila tiene un separador de más (un valor sin
  comillas que lo contiene) o de menos. Corrige la exportación, no el fichero a mano.
- `la carga de dlt falló en load: …`: dlt guarda la carga fallida y la **reintenta al principio de
  la siguiente ejecución**, aunque hayas cambiado el contrato. Corrige la causa y, si el mismo
  error se repite, `make descartar` y vuelve a cargar.
- `dlt no ha cargado …`: falta el recurso de esa tabla en tus huecos (`name=` debe ser el nombre
  de la tabla del contrato).
- `no se pudo conectar con la base` (también tras `la carga de dlt falló en sync`): ¿está
  levantada (`make base`)? ¿Has cambiado el puerto en `.env` sin volver a levantarla?
- El puerto 5440 está ocupado: cambia `PROYECTO_PUERTO` en `.env` y repite `make base`. Si ya hay
  otro proyecto de Docker llamado `l03-proyecto` (otra copia del kit), pon otro
  `COMPOSE_PROJECT_NAME` en `.env`.
- `contrato.yml: …`: el mensaje dice qué tabla o columna está mal; los nombres son los que deja
  dlt (ver «Nombres de columna»).
- Quieres empezar de cero: `make borrar` y después `make base`.

Si aún no tienes datos de tu proyecto, [`ejemplo/`](ejemplo/README.md) genera un proyecto de
ejemplo con semilla para practicar.

La documentación de dlt que se enlaza en el capítulo es la de la versión más reciente en línea;
el kit fija dlt 1.30.0 (`uv.lock`). Si algo no coincide, manda la versión del kit.
