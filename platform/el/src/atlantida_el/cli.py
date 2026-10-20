"""Orden atlantida-el: carga el PMS (origen pms o api) y las fuentes externas en el DWH.

Ejemplos (desde platform/ con Docker: make el; en el anfitrión: uv run atlantida-el …):
  atlantida-el cargar                 # incremental: solo lo nuevo o cambiado
  atlantida-el cargar --reiniciar     # borra lo cargado y el estado y empieza de cero
  atlantida-el estado                 # últimas cargas registradas en meta.carga
  atlantida-el airbyte aplicar [--config FICHERO]   # perfil full: Airbyte como código
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import meta
from .cerrojo import cerrojo
from .config import ConfigEL
from .entorno import cargar_env_file
from .errores import CambioDeOrigen, ErrorDeCarga, ReinicioNecesario, causa_raiz
from .fuente_externa import ProveedorNoDisponible
from .pipeline import ResultadoCarga, cargar_externas, cargar_pms

SALIDA_ERROR, SALIDA_REINICIO = 1, 3


def _informe(nombre: str, r: ResultadoCarga) -> None:
    total = sum(r.filas.values())
    print(f"{nombre}: {len(r.filas)} tablas, {total:,} filas nuevas o cambiadas".replace(",", " "))


def _estado(config: ConfigEL) -> int:
    from datetime import UTC

    for f in reversed(meta.ultimas(config.url_dwh)):
        print(
            f"{f['inicio'].astimezone(UTC):%Y-%m-%d %H:%M} UTC  {f['fuente']:<10} {f['tabla']:<20} "
            f"{f['estado']:<11} {f['filas'] if f['filas'] is not None else '-':>9}"
        )
    return 0


def _airbyte(accion: str, config: ConfigEL, fichero: Path | None = None) -> int:
    import os

    import psycopg

    from .airbyte import (
        ClienteAirbyte,
        cargar_conexiones,
        flujos,
        flujos_de_config,
        preparar_pms,
        quitar_ranura,
        url_origen,
    )
    from .esquema import tablas_desde_catalogo

    if fichero is not None and not fichero.is_file():
        raise ErrorDeCarga(f"No existe la configuración de Airbyte {fichero}.")
    env = dict(os.environ)
    if fichero is not None and accion == "quitar-ranura":  # sin Airbyte: sus hosts no se usan
        env = {"AIRBYTE_ORIGEN_HOST": "-", "AIRBYTE_DESTINO_HOST": "-", **env}
    conf = cargar_conexiones(env, fichero)
    replica = conf["origen"]["configuracion"]["replication_method"]
    url = url_origen(conf) if fichero is not None else config.url_pms
    if accion == "quitar-ranura":
        print(
            "Ranura borrada."
            if quitar_ranura(url, replica["replication_slot"])
            else "No había ranura."
        )
        return 0
    cliente = ClienteAirbyte(
        os.environ.get("AIRBYTE_URL", "http://localhost:8000"),
        os.environ.get("AIRBYTE_CLIENT_ID", ""),
        os.environ.get("AIRBYTE_CLIENT_SECRET", ""),
    )
    if fichero is not None:
        lista = flujos_de_config(conf)
        cdc = [f["name"] for f in lista if f["syncMode"] == "incremental_deduped_history"]
    else:
        with psycopg.connect(config.url_pms) as c:
            tablas = tablas_desde_catalogo(c)
        lista = flujos(tablas)
        cdc = [n for n, t in tablas.items() if t.disposicion == "merge"]
    if accion == "aplicar":
        preparar_pms(url, replica["publication"], replica["replication_slot"], cdc)
        ids = cliente.aplicar(conf, lista)
        print(f"Airbyte configurado: {ids}")
        return 0
    ids = cliente.aplicar(conf, lista)
    print(
        f"Sincronización lanzada (trabajo {cliente.sincronizar(ids['conexion'])}); "
        "después: make dbt MOTOR_EL=airbyte"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="atlantida-el",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="orden", required=True)
    c = sub.add_parser("cargar", help="carga incremental del PMS y de las fuentes externas")
    c.add_argument("--solo", choices=["pms", "externas"])
    c.add_argument(
        "--reiniciar",
        action="store_true",
        help="borra lo cargado y el estado incremental y carga desde cero",
    )
    sub.add_parser("estado", help="últimas cargas registradas en meta.carga")
    ab = sub.add_parser("airbyte", help="perfil full: Airbyte configurado como código")
    ab.add_argument("accion", choices=["aplicar", "sincronizar", "quitar-ranura"])
    ab.add_argument(
        "--config",
        type=Path,
        help="otra configuración como código (p. ej. laboratorio/l03/kit/airbyte.yml), con sus "
        "propias tablas",
    )
    args = ap.parse_args(argv)
    try:
        cargar_env_file()
        config = ConfigEL.desde_entorno()
        if args.orden == "airbyte":
            return _airbyte(args.accion, config, args.config)
        if args.orden == "estado":
            return _estado(config)
        with cerrojo(config.url_dwh):  # una sola ejecución a la vez escribe en el almacén
            if args.solo != "externas":
                _informe(
                    f"PMS (origen {config.origen})", cargar_pms(config, reiniciar=args.reiniciar)
                )
            if args.solo != "pms":
                r = cargar_externas(config, reiniciar=args.reiniciar)
                _informe("Fuentes externas", r)
        if args.solo != "pms" and (aviso := meta.aviso_rate_shopper(config.url_dwh)):
            print(aviso)
    except (CambioDeOrigen, ReinicioNecesario) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return SALIDA_REINICIO
    except (ErrorDeCarga, ProveedorNoDisponible, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return SALIDA_ERROR
    except Exception as exc:
        # Una pieza del laboratorio por completar (un esqueleto con huecos): su pista, sin traza.
        raiz = causa_raiz(exc)
        if not isinstance(raiz, NotImplementedError):
            raise
        print(f"ERROR: {raiz} (pieza del laboratorio sin completar)", file=sys.stderr)
        return SALIDA_ERROR
    return 0
