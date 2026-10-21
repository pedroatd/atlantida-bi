"""Orden atlantida-dbt: dbt con el proyecto de Atlántida y utilidades del almacén.

atlantida-dbt dbt build                  # cualquier orden de dbt (build, test, snapshot…)
atlantida-dbt manifest                   # manifest del código (sin base de datos)
atlantida-dbt estado-prod                # estado de prod (parse) si aún no se ha construido prod
atlantida-dbt generar [--comprobar]      # ficheros derivados de atlantida.yml (seeds, macros)
atlantida-dbt logro                      # objetivo_logro frente a atlantida_def (1 si difiere)
atlantida-dbt semantica --metricas revpar,adr [--por anio|mes|dia] [--por-hotel]
atlantida-dbt pipeline [--reiniciar]     # carga incremental (PMS y externas) y dbt build
atlantida-dbt linea-base [--escribir --cambio "…"]
                                         # línea base de los objetivos (periodo base, almacén;
                                         # solo escribe con el PMS de escala 1)
atlantida-dbt historico --confirmar [--paso mes|trimestre|semestre] [--hasta AAAA-MM-DD]
                                         # BORRA el PMS y lo vuelve a sembrar mes a mes (SCD2)
"""

from __future__ import annotations

import argparse
import sys
from contextlib import nullcontext
from datetime import date

from .ejecutar import SeleccionVacia, dbt, destino

SALIDA_REINICIO = 3  # como atlantida-el: hace falta volver a cargar desde cero


def _dbt(args) -> int:
    import os

    from atlantida_el.cerrojo import cerrojo
    from atlantida_el.config import ConfigEL
    from atlantida_el.errores import ErrorDeCarga, ReinicioNecesario

    from . import sal
    from .ejecutar import ORDENES_QUE_ESCRIBEN

    argumentos = args.argumentos or ["build"]
    try:
        # Las órdenes que escriben esperan a que ninguna otra ejecución escriba en el almacén.
        with (
            cerrojo(ConfigEL.desde_entorno().url_dwh)
            if argumentos[0] in ORDENES_QUE_ESCRIBEN
            else nullcontext()
        ):
            if argumentos[0] in sal.ORDENES_CON_SAL and destino(argumentos, os.environ) == "prod":
                # como pipeline: no mezclar en el almacén seudónimos de dos sales
                sal.comprobar(ConfigEL.desde_entorno().url_dwh, os.environ)
            return 0 if dbt(argumentos, permitir_fallo=True).success else 1
    except ReinicioNecesario as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return SALIDA_REINICIO
    except (SeleccionVacia, ErrorDeCarga) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def _manifest(args) -> int:
    from .estado import generar_manifest_codigo

    print(f"escrito: {generar_manifest_codigo()}")
    return 0


def _estado_prod(args) -> int:
    import os

    from .estado import generar_estado_prod
    from .rutas import estado_prod

    existente = estado_prod() / "manifest.json"
    if existente.is_file() and not args.forzar:
        print(f"Ya hay un estado de prod ({existente}): no se toca. Usa --forzar para sustituirlo.")
        return 0
    print(f"escrito: {generar_estado_prod(os.environ, forzar=args.forzar)}")
    return 0


def _generar(args) -> int:
    from .generar import DESTINO_VIZ, comprobar, generar
    from .rutas import PROYECTO

    if args.comprobar:
        pendientes = comprobar(PROYECTO, DESTINO_VIZ)
        for p in pendientes:
            print(f"desactualizado: {p}")
        return 1 if pendientes else 0
    for f in generar(PROYECTO, DESTINO_VIZ):
        print(f"escrito: {f}")
    return 0


def _logro(args) -> int:
    import os
    from urllib.parse import quote

    from . import linea_base, logro

    url = (
        f"postgresql://{quote(os.environ.get('TRANSFORMER_USER', 'transformer'), safe='')}:"
        f"{quote(os.environ.get('TRANSFORMER_PASSWORD', ''), safe='')}@"
        f"{os.environ.get('DWH_HOST', '127.0.0.1')}:"
        f"{os.environ.get('DWH_PORT_INTERNO') or os.environ.get('DWH_PORT') or '5434'}/"
        f"{os.environ.get('DWH_DB', 'dwh')}"
    )
    # La línea base del documento solo se compara si el PMS de origen es la simulación de
    # referencia (S10): con otra escala o semilla, el almacén tiene su propia base.
    try:
        from atlantida_el.config import ConfigEL

        problema = linea_base.origen_no_valido(ConfigEL.desde_entorno())
    except Exception as exc:  # sin PMS accesible no se sabe de qué simulación sale el almacén
        problema = f"no se pudo leer el PMS de origen ({type(exc).__name__})"
    if problema:
        print(f"Línea base del documento no comparada: {problema}.")
    errores = logro.comprobar_logro(url, linea_base=problema is None)
    for e in errores:
        print(e)
    print(
        "objetivo_logro coincide con atlantida_def."
        if not errores
        else f"{len(errores)} discrepancias."
    )
    return 1 if errores else 0


def _semantica(args) -> int:
    from atlantida_def import cargar_definicion
    from atlantida_def.edicion import de_capa

    from .ejecutar import ErrorDbt

    # La capa semántica llega a la edición del alumnado con el L7 (como make semantica).
    semantica = de_capa("atlantida_dbt.semantica", "atlantida-dbt semantica", "L7")

    h = cargar_definicion().horizonte_simulado
    desde = date.fromisoformat(args.desde) if args.desde else h.inicio
    hasta = date.fromisoformat(args.hasta) if args.hasta else h.fin
    peticion = (args.metricas.split(","), desde, hasta, args.por, args.por_hotel)
    try:
        if args.explicar:
            print(semantica.explicar(*peticion))
            return 0
        df = semantica.consultar(*peticion)
    except ErrorDbt as exc:
        print(f"ERROR: {_explicar_semantica(str(exc))}", file=sys.stderr)
        return 1
    print(
        f"Del {desde} al {hasta}, {'una fila por hotel' if args.por_hotel else 'toda la cadena'}:"
    )
    print(df.to_string(index=False))
    return 0


def _explicar_semantica(texto: str) -> str:
    """MetricFlow vuelca una traza en inglés si no llega al DWH: se resume en una línea."""
    if "password authentication failed" in texto or "no password supplied" in texto:
        return "El DWH rechazó la contraseña del rol transformer: revisa TRANSFORMER_PASSWORD."
    if any(t in texto for t in ("Connection refused", "could not connect", "OperationalError")):
        return (
            "No se puede conectar con el DWH (¿has ejecutado make up? ¿es correcto DWH_PORT?). "
            "Con make usa el puerto interno; con uv run, el publicado en platform/.env."
        )
    return texto


def _pipeline(args) -> int:
    from atlantida_el import meta
    from atlantida_el.config import ConfigEL
    from atlantida_el.errores import CambioDeOrigen, ErrorDeCarga, ReinicioNecesario

    from .ejecutar import ErrorDbt
    from .orquestacion import pipeline

    try:
        config = ConfigEL.desde_entorno()
        pipeline(config, reiniciar=args.reiniciar)
        aviso = meta.aviso_rate_shopper(config.url_dwh)
    except (CambioDeOrigen, ReinicioNecesario) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return SALIDA_REINICIO
    except (ErrorDeCarga, ErrorDbt) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if aviso:
        print(aviso)
        print(
            "Pipeline terminado con avisos: datos del PMS cargados y almacén construido, "
            "sin tarifas de mercado nuevas (rate shopper)."
        )
    else:
        print("Pipeline terminado: datos cargados y almacén construido.")
    return 0


def _historico(args) -> int:
    from atlantida_def.edicion import del_simulador

    # Del profesor: sin el simulador (edición del alumnado), EdicionSinSimulador lo explica.
    Config = del_simulador("config", "make historico").Config
    from atlantida_el.config import ConfigEL
    from atlantida_el.errores import ErrorDeCarga

    from .ejecutar import ErrorDbt
    from .orquestacion import DestinoNoSeguro, aviso_historico, destinos, historico

    try:
        config_sim, config_el = Config.desde_entorno(), ConfigEL.desde_entorno()
        objetivos, problema = destinos(config_sim, config_el), None
    except DestinoNoSeguro as exc:
        objetivos, problema = None, exc
    except ValueError as exc:
        print(f"{aviso_historico()}\nERROR: {exc}", file=sys.stderr)
        return 2
    if problema or not args.confirmar:
        print(aviso_historico(objetivos, config_sim.escala), file=sys.stderr)
        if problema:
            print(f"ERROR: {problema}", file=sys.stderr)
        else:
            print("Repite la orden con --confirmar (make historico lo pregunta).", file=sys.stderr)
        return 2
    try:
        cortes = historico(config_sim, config_el, paso=args.paso, hasta=args.hasta)
    except DestinoNoSeguro as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (ErrorDeCarga, ErrorDbt) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Histórico reconstruido en {len(cortes)} pasos ({cortes[0]} → {cortes[-1]}).")
    return 0


def _linea_base(args) -> int:
    from atlantida_def.carga import _ruta_por_defecto

    from . import linea_base
    from .orquestacion import url_transformer

    valores = linea_base.calcular_linea_base(url_transformer())
    d = linea_base.cargar_definicion()
    pendientes, iguales, distintas = linea_base.clasificar(valores, d)
    for objetivo, kpis in valores.items():
        print(f"{objetivo}: {kpis}" + (" (ya fijada)" if objetivo in iguales else ""))
    if distintas:
        for objetivo, kpis in distintas.items():
            for kpi, fijado, calculado in kpis:
                print(
                    f"ERROR: {objetivo}.{kpi}: el documento fija {fijado} y el almacén da "
                    f"{calculado}.",
                    file=sys.stderr,
                )
        print(
            "La línea base ya fijada no coincide con el almacén: revisa el almacén (escala 1, "
            "semilla por defecto) o registra el cambio de definición en una versión nueva.",
            file=sys.stderr,
        )
        return 1
    if not args.escribir:
        return 0
    if not args.cambio:
        print("ERROR: --escribir necesita --cambio (texto del historial).", file=sys.stderr)
        return 2
    if not pendientes:
        print("Línea base ya fijada: nada que escribir.")
        return 0
    if not args.forzar:
        from atlantida_el.config import ConfigEL
        from atlantida_el.errores import ErrorDeCarga

        try:
            problema = linea_base.origen_no_valido(ConfigEL.desde_entorno())
        except ErrorDeCarga as exc:
            problema = f"no se pudo leer el PMS de origen: {str(exc).rstrip('.')}"
        if problema:
            print(f"ERROR: no se escribe la línea base: {problema}.", file=sys.stderr)
            return 2
    # La entrada nueva del historial lleva la fecha de aprobación vigente: el historial
    # termina en la aprobación del documento.
    linea_base.escribir_linea_base(
        pendientes,
        _ruta_por_defecto("atlantida.yml"),
        args.version or _siguiente_version(d.version),
        d.documento.fecha_aprobacion,
        args.cambio,
    )
    print(
        "atlantida.yml actualizado: ejecuta atlantida-dbt generar y las pruebas de la definición."
    )
    return 0


def _siguiente_version(version: str) -> str:
    """«2.5.1» → «2.5.2»: el cambio de la línea base no altera ninguna definición."""
    mayor, menor, parche = (int(x) for x in version.split("."))
    return f"{mayor}.{menor}.{parche + 1}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="atlantida-dbt",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="orden", required=True)
    p = sub.add_parser("dbt", help="ejecuta dbt con el proyecto de Atlántida (p. ej. dbt build)")
    p.add_argument("argumentos", nargs=argparse.REMAINDER)
    p.set_defaults(funcion=_dbt)
    mf = sub.add_parser(
        "manifest", help="manifest del código (dbt parse) para Dagster y el diccionario"
    )
    mf.set_defaults(funcion=_manifest)
    ep = sub.add_parser(
        "estado-prod", help="genera el estado de prod (dbt parse) para --defer y state:modified"
    )
    ep.add_argument("--forzar", action="store_true", help="sustituye un estado ya existente")
    ep.set_defaults(funcion=_estado_prod)
    g = sub.add_parser("generar", help="regenera los ficheros derivados de atlantida.yml")
    g.add_argument(
        "--comprobar", action="store_true", help="solo comprueba (código 1 si no están al día)"
    )
    g.set_defaults(funcion=_generar)
    lg = sub.add_parser("logro", help="comprueba que objetivo_logro coincide con atlantida_def")
    lg.set_defaults(funcion=_logro)
    se = sub.add_parser("semantica", help="consulta métricas de la capa semántica (MetricFlow)")
    se.add_argument("--metricas", required=True, help="lista separada por comas, p. ej. revpar,adr")
    se.add_argument("--por", choices=["anio", "mes", "dia"], default="anio")
    se.add_argument("--por-hotel", action="store_true")
    se.add_argument("--desde", help="AAAA-MM-DD (por omisión, inicio del histórico simulado)")
    se.add_argument("--hasta", help="AAAA-MM-DD (por omisión, fin del histórico simulado)")
    se.add_argument(
        "--explicar", action="store_true", help="muestra el SQL de MetricFlow sin ejecutarlo"
    )
    se.set_defaults(funcion=_semantica)
    pp = sub.add_parser("pipeline", help="carga incremental y dbt build (repetible sin duplicar)")
    pp.add_argument("--reiniciar", action="store_true", help="vuelve a cargar todo desde cero")
    pp.set_defaults(funcion=_pipeline)
    hi = sub.add_parser(
        "historico", help="reconstruye PMS y DWH paso a paso (historia SCD2 completa)"
    )
    hi.add_argument("--confirmar", action="store_true", help="necesario: vuelve a sembrar el PMS")
    hi.add_argument("--paso", choices=["mes", "trimestre", "semestre"], default="mes")
    hi.add_argument("--hasta", type=date.fromisoformat, metavar="AAAA-MM-DD")
    hi.set_defaults(funcion=_historico)
    lb = sub.add_parser("linea-base", help="línea base de los objetivos calculada en el almacén")
    lb.add_argument(
        "--escribir", action="store_true", help="la escribe en atlantida.yml (versión nueva)"
    )
    lb.add_argument(
        "--version", default=None, help="versión nueva del documento (por omisión, la siguiente)"
    )
    lb.add_argument("--cambio", default="", help="texto del historial del documento")
    lb.add_argument(
        "--forzar",
        action="store_true",
        help="escribe aunque el PMS de origen no sea el de escala 1 y semilla por defecto",
    )
    lb.set_defaults(funcion=_linea_base)
    args = ap.parse_args(argv)
    from atlantida_el.entorno import cargar_env_file
    from atlantida_el.errores import ErrorDeCarga

    try:
        cargar_env_file()  # como atlantida-sim: sin pisar lo que ya esté en el entorno
    except ErrorDeCarga as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    from atlantida_def.edicion import CapaPosterior, EdicionSinSimulador

    try:
        return args.funcion(args)
    except (EdicionSinSimulador, CapaPosterior) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return exc.codigo_salida
