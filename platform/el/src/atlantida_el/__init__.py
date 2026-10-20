"""Cargas (EL) de Atlántida Hoteles: del PMS (base local o API de cambios) y de las fuentes
externas a las capas raw_pms y raw_ext del DWH, con dlt."""

import os

# Perfil lite sin red: dlt no envía telemetría, se use como se use el paquete.
os.environ.setdefault("RUNTIME__DLTHUB_TELEMETRY", "false")
# dlt avisa en inglés de detalles internos (fusión de esquemas Arrow, columnas reflejadas) que no
# son fallos: se muestran solo sus errores. Un fallo real sigue llegando como excepción y como
# registro en meta.carga. Para depurar: RUNTIME__LOG_LEVEL=WARNING (o INFO) en el entorno.
os.environ.setdefault("RUNTIME__LOG_LEVEL", "ERROR")

__version__ = "0.1.0"
