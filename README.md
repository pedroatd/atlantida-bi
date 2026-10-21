# Atlántida Hoteles: plataforma de BI (edición del alumnado)

Este repositorio es la plataforma de *business intelligence* de **Atlántida Hoteles**, la cadena
hotelera ficticia de los apuntes de BI del máster de la Universidad de La Laguna, en su **edición
del alumnado**. Llega **por etapas**: cada laboratorio del libro publica una versión nueva con lo
que ese laboratorio necesita. Las capas de laboratorios anteriores vienen como referencia; lo que
construiste en un laboratorio sigue siendo tuyo salvo que tu profesor publique su referencia. En el
laboratorio actual encontrarás **piezas para construir**: ficheros con huecos y pruebas que te dicen
cuándo están bien. En Python, los huecos son funciones que lanzan `NotImplementedError` con una
pista; en un modelo SQL de dbt, comentarios `-- COMPLETA:` con una pista y un `where false` que deja
el modelo vacío, pero compilable, hasta que lo completas.

El sistema operacional de los hoteles (el PMS) no se ejecuta en tu equipo: lo sirve **tu
profesor** por una API de cambios, y tu plataforma carga desde ella sus datos en tu almacén.

El libro, con los capítulos de teoría y los laboratorios (Parte VII), está en
<https://pedroatd.github.io/apuntes-bi/>. Cada laboratorio explica qué construir aquí y cómo
comprobarlo.

## Requisitos

- [Docker](https://docs.docker.com/get-started/get-docker/) con Docker Compose. En Windows y macOS,
  Docker Desktop (en Windows, con la integración WSL2 activada).
- `make` (en macOS, `xcode-select --install`; en Windows, dentro de WSL2: `sudo apt install make`).
- `git`.
- [uv](https://docs.astral.sh/uv/), para el entorno de Python 3.12 y las pruebas.

En Windows con WSL2, clona el repositorio dentro del sistema de ficheros de Linux (por ejemplo, en
`~/`), no en `/mnt/c`: es mucho más rápido y evita problemas de permisos.

## Inicio rápido

1. Crea tu configuración a partir del ejemplo:

   ```bash
   cp platform/.env.example platform/.env && chmod 600 platform/.env
   ```

2. Edita `platform/.env` y rellena lo que te da tu profesor: `SIM_API_URL` (la URL de la API de
   cambios, termina en `/v1`), `SIM_API_TOKEN` (tu token; no lo compartas ni lo subas a git) y
   `RS_URL` (la URL del *rate shopper*, el proveedor de tarifas de la competencia). `ORIGEN_PMS`
   ya vale `api`.

3. Levanta la plataforma y comprueba que todo responde:

   ```bash
   make -C platform up
   make -C platform smoke
   ```

   `make -C platform help` lista las órdenes de esta etapa. Si pides una que llega con un
   laboratorio posterior, `make` te dice con cuál.

4. Sigue el laboratorio en el libro: las piezas que tienes que construir y cómo comprobarlas
   (con `uv run pytest <ruta de las pruebas>` o con el comprobador del laboratorio)
   están indicadas allí.

## Cómo se actualiza

Cada laboratorio es una publicación nueva de este repositorio (una etiqueta `lab-NN`). Trabaja
siempre en una rama tuya (`git switch -c mi-trabajo`), no en `main`: `main` solo recibe las
publicaciones. Para recibir una, guarda antes tu trabajo en tu rama (la primera orden la crea si
no la tenías) y fusiona en ella la publicación nueva (`origin/main`):

```bash
git switch mi-trabajo 2>/dev/null || git switch -c mi-trabajo
git add -A && git commit -m "mi trabajo"   # platform/.env no se sube; «nothing to commit» no es un error
git fetch origin
git merge origin/main
```

Lo que hayas construido en los ficheros con huecos puede chocar con la versión nueva (por
ejemplo, si tu profesor publica la referencia de una pieza que completaste tú). Entonces
`git merge` se para y `git status` lista los ficheros en conflicto: decide en cada uno qué versión
te quedas, y termina con `git add` y `git commit`. El capítulo de cada laboratorio da las órdenes
exactas cuando una publicación trae una referencia (por ejemplo, la del cargador del L3 en el L4).

## Licencias

- El código se publica bajo licencia **MIT** (`LICENSE`).
- El contenido docente se publica bajo **Creative Commons Atribución-NoComercial-CompartirIgual
  4.0** (`LICENSE-CONTENT`).
