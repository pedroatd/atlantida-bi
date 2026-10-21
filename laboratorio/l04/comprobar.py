"""Comprobador de la parte guiada del laboratorio L4 (make -C platform l4-comprobar).

Construye las piezas del modelo dimensional que completas en el laboratorio y ejecuta sus pruebas
(las unitarias de dbt de models/marts/core/_l4_unitarias.yml y las de esquema y singulares que ya
tenían). Después resume, por pieza, una línea:

    brg_reserva_huesped   OK
    dim_huesped           FALLA: dim_huesped_versiones_contiguas
    fct_cargo_folio       sin completar

«sin completar» quiere decir que el modelo aún tiene alguna marca «-- COMPLETA:»: bórrala cuando
resuelvas su hueco. Sale con 0 si todas las piezas están en OK y con 1 si no.

Pasos (dos órdenes de dbt, en el contenedor de la plataforma):

1. build de las piezas (sin pruebas). Lo que leen ya está construido desde el paso 2 del
   laboratorio; si falta algo (dbt dice que una relación no existe), build también de los modelos,
   snapshots y seeds de los que dependen (+pieza), que tarda más: las pruebas unitarias necesitan
   que existan los modelos padre;
2. test de las piezas: sus pruebas unitarias y las de datos (también las que comparan con otra
   pieza, como el puente frente a dim_huesped).

Uso: python comprobar.py [--pieza PIEZA] [--proyecto DIR] [--dbt "atlantida-dbt dbt"]
(PIEZA también en la variable L4_PIEZA). No importa el código de la plataforma: lee los resultados
de dbt (target/run_results.json y target/manifest.json) y los ficheros de los modelos.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

# En el orden en que se construyen (el puente lee dim_huesped).
PIEZAS = ("dim_huesped", "brg_reserva_huesped", "fct_cargo_folio")
# En el que se presentan: el orden de dificultad del laboratorio.
ORDEN_LAB = ("brg_reserva_huesped", "dim_huesped", "fct_cargo_folio")
MARCA = "-- COMPLETA:"  # la de cada hueco (los comentarios la citan sin los dos puntos)
CARPETA = Path("models/marts/core")
FALLOS = {"fail", "error", "runtime error", "skipped"}
# El mensaje de PostgreSQL cuando una pieza lee una relación que aún no está construida.
FALTA_RELACION = re.compile(r'relation "[^"]+" does not exist')


def _pieza_de(uid: str, nodo: dict, piezas: tuple[str, ...]) -> list[str]:
    """Piezas a las que se atribuye un resultado: el modelo, la prueba unitaria del modelo o la
    prueba de datos unida a él (attached_node) o, si no lo está, la de las piezas que lee."""
    partes = uid.split(".")
    if partes[0] == "model":
        return [partes[-1]] if partes[-1] in piezas else []
    if partes[0] == "unit_test":
        return [partes[2]] if len(partes) > 3 and partes[2] in piezas else []
    unida = (nodo.get("attached_node") or "").rsplit(".", 1)[-1]
    if unida in piezas:
        return [unida]
    padres = [n.rsplit(".", 1)[-1] for n in nodo.get("depends_on", {}).get("nodes", [])]
    if lee := [p for p in piezas if p in padres]:
        return lee
    return [p for p in piezas if p in uid]  # sin manifest: por el nombre de la prueba


def _nombre(uid: str, nodo: dict) -> str:
    if nodo.get("name"):
        return nodo["name"]
    partes = uid.split(".")
    return partes[3] if partes[0] == "unit_test" and len(partes) > 3 else partes[2]


def resumir(
    run_results: dict,
    esqueletos: dict[str, bool],
    manifest: dict | None = None,
    sin_completar: dict[str, bool] | None = None,
) -> list[tuple[str, str]]:
    """(pieza, veredicto) por cada pieza de «esqueletos» (pieza → aún tiene «-- COMPLETA:»), en el
    orden del laboratorio. Veredicto: "OK", "sin completar" o "FALLA: <prueba o modelo>".
    «sin_completar» (por omisión, «esqueletos») es el estado de todas las piezas, también las que
    no se resumen (PIEZA=…): una prueba que falla y lee otra pieza aún sin completar lo dice."""
    todas = sin_completar if sin_completar is not None else esqueletos
    nodos = (manifest or {}).get("nodes", {}) | (manifest or {}).get("unit_tests", {})
    piezas = tuple(esqueletos)
    vistos: dict[str, int] = dict.fromkeys(piezas, 0)
    unitarias: dict[str, int] = dict.fromkeys(piezas, 0)
    fallos: dict[str, list[str]] = {p: [] for p in piezas}
    for r in run_results.get("results", []):
        uid, estado = r["unique_id"], str(r.get("status", "")).lower()
        nodo = nodos.get(uid, {})
        for p in _pieza_de(uid, nodo, piezas):
            vistos[p] += 1
            unitarias[p] += uid.startswith("unit_test.")
            if estado not in FALLOS:
                continue
            nombre = _nombre(uid, nodo)
            if uid.startswith("model."):
                motivo = "no se ha construido" if estado == "skipped" else "error de dbt"
                mensaje = (r.get("message") or "").strip().splitlines()
                nombre += f" ({motivo}{': ' + mensaje[0] if mensaje else ''})"
            elif estado == "skipped":
                nombre += " (no se ha ejecutado)"
            otras = [
                o
                for o in _pieza_de(uid, {"depends_on": nodo.get("depends_on", {})}, tuple(todas))
                if o != p and todas.get(o)
            ]
            if otras:
                nombre += f" (lee {', '.join(otras)}, aún sin completar)"
            fallos[p].append(nombre)
    salida = []
    for p in sorted(piezas, key=lambda x: ORDEN_LAB.index(x) if x in ORDEN_LAB else 99):
        if esqueletos[p]:
            salida.append((p, "sin completar"))
        elif fallos[p]:
            salida.append((p, "FALLA: " + ", ".join(fallos[p])))
        elif not vistos[p]:
            salida.append((p, f"FALLA: dbt no ha ejecutado {p}"))
        elif not unitarias[p]:  # sin sus pruebas unitarias no hay nada que dé la pieza por buena
            salida.append((p, f"FALLA: no se ha ejecutado ninguna prueba unitaria de {p}"))
        else:
            salida.append((p, "OK"))
    return salida


def falta_lo_que_leen(run_results: dict, piezas) -> bool:
    """¿Alguna pieza no se ha construido porque lee una relación que no existe? Entonces hay que
    construir también lo que está aguas arriba (+pieza)."""
    for r in run_results.get("results", []):
        uid = r.get("unique_id", "")
        if (
            uid.startswith("model.")
            and uid.rsplit(".", 1)[-1] in piezas
            and str(r.get("status", "")).lower() == "error"
            and FALTA_RELACION.search(r.get("message") or "")
        ):
            return True
    return False


def _leer_json(ruta: Path) -> dict | None:
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _dbt(orden: list[str], args: list[str], proyecto: Path) -> dict | None:
    """Ejecuta dbt (su salida va a la pantalla) y devuelve su run_results.json, o None si dbt no
    llegó a escribirlo."""
    rr = proyecto / "target/run_results.json"
    rr.unlink(missing_ok=True)
    print("$ dbt " + " ".join(args), flush=True)
    try:
        subprocess.run([*orden, *args], cwd=proyecto, check=False)
    except OSError as e:
        print(f"No se ha podido ejecutar dbt ({orden[0]}): {e}", file=sys.stderr)
        return None
    return _leer_json(rr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--pieza", default=os.environ.get("L4_PIEZA") or None)
    ap.add_argument("--proyecto", type=Path, default=Path(os.environ.get("DBT_PROJECT_DIR", ".")))
    ap.add_argument(
        "--dbt", default="atlantida-dbt dbt", help="orden de dbt (por omisión, %(default)s)"
    )
    a = ap.parse_args(argv)
    if a.pieza and a.pieza not in PIEZAS:
        print(
            f"No hay ninguna pieza «{a.pieza}» en el L4. Las piezas son: {', '.join(ORDEN_LAB)} "
            "(PIEZA=<pieza>, o nada para las tres).",
            file=sys.stderr,
        )
        return 2
    piezas = [p for p in PIEZAS if not a.pieza or p == a.pieza]
    esqueletos = {}
    for p in piezas:
        ruta = a.proyecto / CARPETA / f"{p}.sql"
        try:
            esqueletos[p] = MARCA in ruta.read_text(encoding="utf-8")
        except OSError:
            print(f"No encuentro el modelo {ruta}.", file=sys.stderr)
            return 1
    # El estado de las tres, para avisar de una prueba que lee otra pieza aún sin completar.
    todas = dict(esqueletos)
    for p in PIEZAS:
        if p not in todas:
            try:
                todas[p] = MARCA in (a.proyecto / CARPETA / f"{p}.sql").read_text(encoding="utf-8")
            except OSError:
                pass
    orden = shlex.split(a.dbt)

    def construir(con_padres: bool) -> list[str]:
        return [
            "build", "--select", *(f"+{p}" if con_padres else p for p in piezas),
            "--resource-type", "model", "--resource-type", "snapshot", "--resource-type", "seed",
        ]  # fmt: skip

    probar = ["test", "--select", *piezas, "--indirect-selection", "buildable"]
    resultados: list[dict] = []
    pasos = [construir(False), probar]
    while pasos:
        args = pasos.pop(0)
        rr = _dbt(orden, args, a.proyecto)
        if rr is None:
            print(
                "\ndbt no ha llegado a ejecutar nada (mira su mensaje de arriba: suele ser un "
                "error de sintaxis o de Jinja en un modelo). Corrígelo y vuelve a comprobar.",
                file=sys.stderr,
            )
            return 1
        if args == construir(False) and falta_lo_que_leen(rr, piezas):
            print(
                "\nAún no está construido algo que leen las piezas: lo construyo también (tarda "
                "más; la próxima vez ya estará).",
                flush=True,
            )
            pasos.insert(0, construir(True))
            continue
        resultados += rr.get("results", [])
    manifest = _leer_json(a.proyecto / "target/manifest.json")
    veredictos = resumir({"results": resultados}, esqueletos, manifest, todas)
    ancho = max(len(p) for p, _ in veredictos)
    print("\nLaboratorio L4, parte guiada:")
    for p, v in veredictos:
        print(f"  {p:<{ancho}}  {v}")
    todo = all(v == "OK" for _, v in veredictos)
    if not todo:
        print("\nCompleta los huecos «-- COMPLETA:» de cada pieza y vuelve a comprobar.")
    return 0 if todo else 1


if __name__ == "__main__":
    sys.exit(main())
