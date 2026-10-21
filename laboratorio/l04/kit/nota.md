# Nota de diseño: <tu proyecto>

Una página. Sustituye cada `<…>`; `nota_ejemplo.md` tiene una resuelta de otro dominio.

## Matriz bus

| Proceso (hecho) | <dimensión 1> | <dimensión 2> | <dimensión 3> |
|---|---|---|---|
| <proceso 1> (`fct_…`) | x | x | |
| <proceso 2> (`fct_…`) | x | | x |

## Hechos

- `fct_<proceso>`: una fila por <…>. Grano: `[<columnas>]` (como en `modelo.yml`). Tipo:
  <transacción / instantánea periódica / instantánea acumulativa>. Medidas: <medida>
  (<aditiva / semiaditiva / no aditiva>, porque <…>).

## Dimensiones y SCD por atributo

- `dim_<entidad>` (clave natural `<…>`): <atributo> tipo <1 o 2>, porque <la pregunta de negocio>.
  Historia desde `raw.<tabla>` con `strategy: <timestamp o check>` <y, con check, su limitación:
  la versión empieza al ejecutar el snapshot>.

## Datos personales

- `<tabla>.<columna>`: <seudonimizada / generalizada (cómo) / no se usa>, porque <…>.

## Decisiones y limitaciones

- <claves opcionales, miembros −1 y −2, borrados en el origen, lo que el comprobador no ve…>
