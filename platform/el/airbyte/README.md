# Airbyte con `abctl` (perfil `full`)

Alternativa a dlt para el tramo de carga (EL). dlt es una **librería** de Python que ejecutas
desde la línea de órdenes; Airbyte es un **servicio** con interfaz web, un catálogo de conectores
y un planificador propio. Aquí lo instalas en un Kubernetes local con `abctl` y lo configuras
como código (`conexiones.yml`), de modo que el resultado es repetible.

Versiones fijadas: abctl v0.30.4 y chart de Helm 2.3.0 (verificadas el 2026-10-05).

Airbyte sigue usando el propietario del PMS: la replicación lógica (CDC) necesita crear la publicación y la ranura.

## Requisitos

- Perfil `full` y al menos 16 GB de RAM.
- Docker con permisos para crear un clúster Kubernetes dentro de Docker (kind, que gestiona `abctl`).
- La plataforma levantada: `make up PROFILE=full`.
- Airbyte no hace falta para el perfil `lite` ni para los laboratorios básicos: dlt es el camino por defecto.

## Pasos (desde `platform/`)

1. `make up PROFILE=full`
2. `make airbyte-instalar`: descarga abctl, comprueba su SHA-256 e instala Airbyte (tarda varios minutos).
3. Ejecuta `./el/airbyte/.bin/abctl local credentials` y copia el identificador y el secreto de
   cliente a `AIRBYTE_CLIENT_ID` y `AIRBYTE_CLIENT_SECRET` de tu `.env`. No los compartas ni los subas al repositorio.
4. `make airbyte-configurar`: crea o actualiza el origen, el destino y la conexión. Es idempotente.
5. `make airbyte-sincronizar`: lanza una sincronización.
6. `make dbt MOTOR_EL=airbyte`: dbt lee `raw_pms_airbyte` en lugar de `raw_pms`.

## Efectos fuera del repositorio

- `abctl local install` escribe en `~/.airbyte` (y el kubeconfig asociado) y publica la interfaz en el puerto 8000.
- `make airbyte-configurar` conecta el nodo de Airbyte a la red de Docker Compose (`docker network connect`) para que alcance
  `pms-db` y `dwh`. Si reinicias la plataforma, vuelve a ejecutarlo. `make down` no deshace esa conexión.
- La suma SHA-256 de abctl procede de la misma publicación de GitHub que el binario: detecta descargas dañadas, no una publicación comprometida.

## CDC: publicación y ranura lógicas

El origen usa captura de cambios (CDC) de PostgreSQL. Necesita `wal_level=logical` (ya lo
configura la plataforma), una **publicación** (qué tablas se replican; solo las que tienen
clave primaria) y una **ranura de replicación** (marcador de hasta dónde ha leído Airbyte del
registro de transacciones o WAL). Las tablas sin clave van por recarga completa.

**Aviso:** una ranura sin consumidor retiene WAL y el disco del PMS crece sin límite. Cuando
dejes de usar Airbyte ejecuta `make airbyte-quitar-ranura`.

## Columnas técnicas

Airbyte añade `_airbyte_raw_id`, `_airbyte_extracted_at` y `_airbyte_meta` a cada tabla de
`raw_pms_airbyte`. Según la versión de su destino Postgres, guarda además tablas crudas en
`airbyte_internal`: desde la 3.0.0 escribe directamente en las tablas finales, sin ellas (la
versión del conector no está fijada: la da el catálogo de Airbyte). La capa de staging usa
`_airbyte_extracted_at` como `cargado_en` y marca `origen_carga = 'airbyte'` cuando
`MOTOR_EL=airbyte`; con dlt usa `_loaded_at` y `_origen`.

## Comparar con dlt

```sql
select count(*) from raw_pms.reservation;
select count(*) from raw_pms_airbyte.reservation;
```

Tras cargar el mismo estado del PMS, los recuentos deben coincidir.

## Desinstalar

`./el/airbyte/.bin/abctl local uninstall` (y `make airbyte-quitar-ranura`).
