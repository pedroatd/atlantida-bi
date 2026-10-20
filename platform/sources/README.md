# Fuentes externas de Atlántida Hoteles

Datos públicos que acompañan al PMS simulado: llegadas de turistas, clima, calendario y tipos de
cambio. Viven en `snapshots/` como CSV versionados, con un `manifiesto.json` que recoge origen,
licencia, atribución, fecha de descarga, filas y huella `sha256` de cada fichero.

## Qué es cada fuente

| Fuente (`instantánea`) | Organismo | Uso en el caso | Columnas | Licencia y atribución |
|---|---|---|---|---|
| `istac_frontur` | ISTAC (FRONTUR-Canarias) | Llegadas mensuales de turistas por isla y país de origen: demanda de contexto | `periodo_mes`, `isla`, `pais_origen`, `llegadas` | Condiciones generales de reutilización del ISTAC (Ley 37/2007): se puede reutilizar citando la fuente. Fuente: Instituto Canario de Estadística (ISTAC) |
| `aemet_diario` | AEMET OpenData (o Open-Meteo) | Lluvia y temperatura máxima diarias de la estación del aeropuerto de cada isla | `fecha`, `isla`, `estacion`, `precipitacion`, `temperatura_maxima` | © AEMET (condiciones de OpenData). Open-Meteo: CC BY 4.0 |
| `festivos` | Librería `holidays` y reglas propias | Festivos nacionales, autonómicos e insulares y vacaciones escolares | ver `manifiesto.json` y `contrato_externo.yml` | MIT (python-holidays) |
| `bce_tipos` | Banco Central Europeo | Tipo de cambio diario del euro frente a GBP, SEK, NOK y DKK | `fecha`, `divisa`, `tipo_cambio` | Reutilización libre citando la fuente |

## Por qué se versionan instantáneas

Para que el caso sea reproducible: todos los alumnos parten de los mismos datos, el simulador no
necesita Internet ni claves y las ejecuciones de integración continua no dependen de servicios
ajenos. La integridad se comprueba con:

```bash
uv run atlantida-fuentes verificar     # OK por cada fuente si sha256 y contrato coinciden
```

## Cómo se actualizan

```bash
make -C platform fuentes               # equivale a: uv run atlantida-fuentes actualizar
```

- Necesita Internet. Si una descarga sale incompleta, se conserva la instantánea anterior.
- AEMET exige una clave gratuita (<https://opendata.aemet.es>), que se lee de la variable de
  entorno `AEMET_API_KEY` (por ejemplo desde `platform/.env`, que no se versiona). Sin clave, o
  si AEMET falla, se usa Open-Meteo (reanálisis ERA5 en las coordenadas de las mismas estaciones,
  estación `OM-<indicativo>`) y el manifiesto lo dice en su nota.
- AEMET limita cada consulta a 6 meses y el número de peticiones por minuto: la descarga se hace
  por trozos, con pausa, y es reanudable si se interrumpe (parciales en `snapshots/.parciales/`,
  fuera del control de versiones). Los tramos de más de un año que AEMET responde sin datos
  (404) se anotan en `snapshots/aemet_sin_datos.json` y no se vuelven a pedir; bórralo para
  forzarlo.
- La clave nunca aparece en URLs, mensajes de error ni ficheros.

## Detalles que conviene saber

- **«Ip» en AEMET** significa precipitación inapreciable (menos de 0,1 mm); se carga como 0.
  «Acum» (precipitación acumulada en otro día) se carga como dato ausente.
- **Vacaciones escolares**: son una aproximación por reglas (fechas orientativas del calendario
  escolar canario), no un calendario oficial curso a curso.
- **Lagunas**: el ISTAC no publica Fuerteventura-Irlanda en mayo de 2021; esa celda falta tal cual
  en la fuente.

## El rate shopper

Un *rate shopper* es un servicio que consulta cada día las tarifas publicadas por los hoteles
competidores para unas fechas de estancia. Un informe tipo STR resume, para el conjunto competitivo
(*compset*) de cada hotel propio, la ocupación, el ADR y el RevPAR de cada día. Aquí ambos los
ofrece un servicio HTTP simulado (FastAPI, `atlantida_sources.rate_shopper`), con las fuentes
`rate_shopper` y `compset_diario` de `platform/definicion/contrato_externo.yml`.

| Endpoint | Qué devuelve |
|---|---|
| `GET /salud` | Estado, si hay datos, y el corte y la huella del simulador |
| `GET /competidores` | Competidores de cada hotel propio |
| `GET /rate_shopper?fecha_consulta=AAAA-MM-DD` | Tarifas consultadas ese día |
| `GET /compset_diario?desde=AAAA-MM-DD&hasta=AAAA-MM-DD` | Informe diario del compset |

```bash
curl "http://127.0.0.1:8001/compset_diario?desde=2025-06-01&hasta=2025-06-30"
curl "http://127.0.0.1:8001/rate_shopper?fecha_consulta=2025-06-01"
```

Los datos los genera `make seed` en el directorio `RS_DATOS_DIR` (por defecto `/datos/mercado`) y
avanzan con el reloj del simulador: el servicio nunca entrega datos posteriores a ese reloj (el
informe del compset de un día se publica al día siguiente).

El proveedor **es poco fiable a propósito**: de vez en cuando responde con error 503, faltan
algunos días sin dato, hay filas repetidas y el formato de los datos cambia desde cierta fecha. No
se dice cuándo ni cuántos: se descubre con los datos, y la ingesta debe tolerarlo. Los fallos son
reproducibles (misma petición, misma respuesta), salvo los 503. Variables: `RS_DATOS_DIR`,
`RS_FAULT_RATE`, `RS_CAMBIO_FORMATO` y `RS_SEED`; si no se definen en `.env`, el servicio usa sus valores por
defecto (que no se publican aquí: son parte de lo que hay que descubrir).

`/salud` y `/competidores` no tienen fallos inyectados: siempre responden. En `/compset_diario`, `desde`
no puede ser posterior a `hasta` y el rango máximo es de 400 días (error 422 en otro caso). Los
valores ausentes se entregan como `null`.
