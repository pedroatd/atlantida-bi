# Proyecto de ejemplo: Red de bibliotecas Lectura Viva

Un proyecto ficticio para practicar el L3 **si aún no tienes los datos de tu proyecto**. Lo genera
un script con semilla, así que la misma semilla da siempre los mismos ficheros:

```bash
uv run python ejemplo/generar.py --salida datos-ejemplo --semilla 7
```

Deja en `datos-ejemplo/` lo que tendría un proyecto real:

| Fichero | Qué es |
|---|---|
| `originales/socio.csv` | Socios de la red (`socio_id, nombre, distrito, alta, actualizado`), separados por `,`. |
| `originales/ejemplar.csv` | Catálogo (`ejemplar_id, titulo, materia, sede, Año, actualizado`), separado por `;` y con BOM, como lo exporta una hoja de cálculo. |
| `sinteticos/prestamos.sql` | La base operacional de préstamos (tablas `prestamo` y `renovacion`), para `make origen F=datos-ejemplo/sinteticos/prestamos.sql`. |
| `sinteticos/prestamos_cambios.sql` | Devoluciones, préstamos nuevos, renovaciones nuevas y algunos préstamos anulados (borrados): aplícalo después de una primera carga para ver la carga incremental (y, en la parte opcional, la captura de cambios). Se puede aplicar más de una vez. |

Copia los dos CSV a `datos/` (`cp datos-ejemplo/originales/*.csv datos/`), restaura
`prestamos.sql` en `proyecto_origen`, escribe tu `contrato.yml` y completa los huecos de
`carga.py` como harías con tu proyecto. Las fechas son de 2031 y los nombres son inventados.

Trae a propósito algunas decisiones que tomar: una cabecera con `ñ` (mira `make columnas`), una
tabla sin columna de última modificación y con clave de dos columnas, y filas que se borran en el
origen.

El ejemplo **no se parece a Atlántida Hoteles a propósito**: en tu proyecto no copiarás la
plataforma del libro, sino que transferirás lo aprendido a otro dominio. Tampoco trae la
solución: la carga la escribes tú.
