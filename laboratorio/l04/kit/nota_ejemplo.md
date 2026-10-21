# Nota de diseño de ejemplo: una cadena de gimnasios (dominio ficticio)

Un ejemplo de la forma de la nota, en un dominio que no es el tuyo: la cadena «Ola», con sus
centros, sus abonados y los accesos por el torno. Tu nota decide por tu proyecto: copiar esta, con
otros nombres, no es una nota tuya.

## Matriz bus

| Proceso (hecho) | abonado | centro | fecha |
|---|---|---|---|
| Accesos por el torno (`fct_acceso`) | x | x | x |
| Ocupación al cierre de cada día (`fct_ocupacion_diaria`) | | x | x |

`dim_centro` y `dim_fecha` son conformadas: las mismas tablas en los dos hechos.

## Hechos

- `fct_acceso`: una fila por paso por el torno. Grano: `[acceso_id]`. Tipo: transacción.
  Medida: `minutos_dentro` (aditiva).
- `fct_ocupacion_diaria`: una fila por centro y día. Grano: `[centro_id, fecha]`. Tipo:
  instantánea periódica. Medida: `abonados_dentro_al_cierre` (semiaditiva: se suma entre centros,
  no entre días; entre días se promedia o se toma el último).

## Dimensiones y SCD por atributo

- `dim_centro` (clave natural `centro_id`): `aforo_maximo`, tipo 2, porque la ocupación se
  compara con el aforo que había ese día; `direccion`, tipo 1 (una corrección). La tabla de
  origen no tiene columna de última modificación: el *snapshot* usa `strategy: check` sobre
  `aforo_maximo`, así que una versión empieza cuando se ejecuta el *snapshot*, no cuando cambió
  el aforo; los días de entre medias toman el aforo anterior.
- `dim_abonado` (clave natural `abonado_id`): todos sus atributos, tipo 1; ningún informe pide
  la historia del abonado.
- `dim_fecha`: calendario generado completo, sin miembro desconocido
  (`miembro_desconocido: false`).

## Datos personales

- `abonado.dni` y `abonado.correo`: seudonimizados los dos, para contar abonados distintos sin
  verlos. `abonado.fecha_nacimiento`: no se usa.

## Decisiones y limitaciones

- Un acceso con una tarjeta que aún no está en `dim_abonado` (dada de alta después de la última
  carga) va a −1: debería existir y no está.
- La limitación de `strategy: check` en `dim_centro`, arriba.
