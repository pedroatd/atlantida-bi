"""Proyecto de ejemplo para el laboratorio L3: la «Red de bibliotecas Lectura Viva» (ficticia).

Genera, con una semilla, lo que tendría un proyecto real:

- originales/socio.csv     socios (separador «,»), como lo exporta el sistema de carnés;
- originales/ejemplar.csv  catálogo (separador «;», con BOM y una cabecera con «ñ»), como lo
  guarda una hoja de cálculo;
- sinteticos/prestamos.sql la base operacional de préstamos (DDL e INSERT) para proyecto_origen:
  préstamos (con su última modificación) y renovaciones (clave de dos columnas y sin columna de
  modificación);
- sinteticos/prestamos_cambios.sql devoluciones, préstamos nuevos, renovaciones nuevas y unos
  préstamos anulados (borrados), para ver la carga incremental (y, en la parte opcional, la
  captura de cambios). Se puede aplicar más de una vez.

Uso: uv run python ejemplo/generar.py --salida DIR [--semilla 7] [--socios 300]
Solo biblioteca estándar; la misma semilla da los mismos bytes.
"""

from __future__ import annotations

import argparse
import csv
import io
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path

NOMBRES = [
    "Ana",
    "Luis",
    "Marta",
    "Jorge",
    "Elena",
    "Pablo",
    "Lucía",
    "Iván",
    "Sara",
    "Raúl",
    "Nora",
    "Hugo",
    "Alba",
    "Darío",
    "Irene",
    "Óscar",
    "Clara",
    "Mario",
    "Eva",
    "Adrián",
]
APELLIDOS = [
    "García",
    "Pérez",
    "Rodríguez",
    "Martín",
    "Sánchez",
    "Díaz",
    "Torres",
    "Ramos",
    "Vega",
    "Cruz",
    "Medina",
    "Castro",
    "Ortega",
    "Rubio",
    "Molina",
    "Nieto",
]
DISTRITOS = ["Norte", "Sur", "Este", "Oeste", "Centro", "Ribera"]
SEDES = ["Sede Central", "Sede Norte", "Sede Ribera", "Bibliobús"]
MATERIAS = ["novela", "poesía", "historia", "ciencia", "infantil", "cómic", "viajes", "cocina"]
SUSTANTIVOS = [
    "jardín",
    "faro",
    "río",
    "silencio",
    "mapa",
    "invierno",
    "puente",
    "espejo",
    "bosque",
    "tren",
    "eco",
    "archivo",
]
COMPLEMENTOS = [
    "de las horas",
    "sin nombre",
    "del sur",
    "de papel",
    "de la tarde",
    "perdido",
    "de los vientos",
    "en calma",
    "de cristal",
    "de medianoche",
]

INICIO = datetime(2031, 1, 1, tzinfo=UTC)
CORTE = datetime(2031, 10, 1, tzinfo=UTC)  # todo lo de prestamos.sql es anterior; los cambios, no


def _instante(rng: random.Random, desde: datetime, hasta: datetime) -> datetime:
    segundos = int((hasta - desde).total_seconds())
    return desde + timedelta(seconds=rng.randrange(segundos) // 60 * 60)


def _fecha(d: datetime) -> str:
    return d.strftime("%Y-%m-%d %H:%M:%S+00")


def _csv(filas: list[list], cabecera: list[str], separador: str) -> str:
    salida = io.StringIO()
    escritor = csv.writer(salida, delimiter=separador, lineterminator="\n")
    escritor.writerow(cabecera)
    escritor.writerows(filas)
    return salida.getvalue()


def _sql(valor) -> str:
    if valor is None:
        return "null"
    if isinstance(valor, int):
        return str(valor)
    if isinstance(valor, datetime):
        valor = _fecha(valor)
    return "'" + str(valor).replace("'", "''") + "'"


def _insert(
    filas: list[tuple],
    bloque: int = 200,
    tabla: str = "prestamo",
    columnas: str = "prestamo_id, socio_id, ejemplar_id, prestado_en, devuelto_en, actualizado",
    clave: str = "prestamo_id",
) -> str:
    partes = []
    for i in range(0, len(filas), bloque):
        valores = ",\n  ".join(
            "(" + ", ".join(_sql(v) for v in f) + ")" for f in filas[i : i + bloque]
        )
        partes.append(
            f"insert into {tabla} ({columnas}) values\n  {valores}\n"
            f"on conflict ({clave}) do nothing;\n"
        )
    return "".join(partes)


DDL = """-- Base operacional de préstamos de la Red de bibliotecas Lectura Viva (ficticia).
-- Restáurala con: make origen F=<carpeta>/sinteticos/prestamos.sql
create table if not exists prestamo (
  prestamo_id  bigint primary key,
  socio_id     bigint not null,
  ejemplar_id  bigint not null,
  prestado_en  timestamptz not null,
  devuelto_en  timestamptz,              -- nulo mientras el ejemplar sigue prestado
  actualizado  timestamptz not null      -- última modificación de la fila
);

-- Cada renovación de un préstamo: no se modifica nunca, pero se borra si se anula el préstamo.
create table if not exists renovacion (
  prestamo_id  bigint not null,
  numero       integer not null,         -- 1.ª, 2.ª… renovación de ese préstamo
  renovado_en  timestamptz not null,
  primary key (prestamo_id, numero)
);

"""

RENOVACION = dict(
    tabla="renovacion", columnas="prestamo_id, numero, renovado_en", clave="prestamo_id, numero"
)


def generar(salida: Path, semilla: int = 7, socios: int = 300) -> None:
    rng = random.Random(semilla)
    originales, sinteticos = salida / "originales", salida / "sinteticos"
    originales.mkdir(parents=True, exist_ok=True)
    sinteticos.mkdir(parents=True, exist_ok=True)

    filas_socio = []
    for i in range(1, socios + 1):
        alta = _instante(rng, INICIO, datetime(2031, 7, 1, tzinfo=UTC))
        actualizado = _instante(rng, alta, CORTE)
        nombre = f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)} {rng.choice(APELLIDOS)}"
        filas_socio.append(
            [i, nombre, rng.choice(DISTRITOS), alta.strftime("%Y-%m-%d"), _fecha(actualizado)]
        )
    (originales / "socio.csv").write_text(
        _csv(filas_socio, ["socio_id", "nombre", "distrito", "alta", "actualizado"], ","),
        encoding="utf-8",
    )

    ejemplares = socios * 4 // 3
    filas_ejemplar = []
    for i in range(1, ejemplares + 1):
        titulo = f"El {rng.choice(SUSTANTIVOS)} {rng.choice(COMPLEMENTOS)}"
        filas_ejemplar.append(
            [
                i,
                titulo,
                rng.choice(MATERIAS),
                rng.choice(SEDES),
                rng.randint(1950, 2030),
                _fecha(_instante(rng, INICIO, CORTE)),
            ]
        )
    cabecera = ["ejemplar_id", "titulo", "materia", "sede", "Año", "actualizado"]
    (originales / "ejemplar.csv").write_text(
        _csv(filas_ejemplar, cabecera, ";"), encoding="utf-8-sig"
    )

    prestamos, pendientes = [], []
    for i in range(1, socios * 4 + 1):
        prestado = _instante(rng, datetime(2031, 2, 1, tzinfo=UTC), CORTE - timedelta(days=1))
        devuelto = prestado + timedelta(days=rng.randint(1, 30), hours=rng.randint(0, 9))
        if devuelto >= CORTE or rng.random() < 0.1:
            devuelto = None
            pendientes.append((i, prestado))
        prestamos.append(
            (
                i,
                rng.randint(1, socios),
                rng.randint(1, ejemplares),
                prestado,
                devuelto,
                devuelto or prestado,
            )
        )
    renovaciones = []
    for i, _, _, prestado, devuelto, _ in prestamos:
        if devuelto is not None and (devuelto - prestado).days > 14 and rng.random() < 0.5:
            renovaciones.append((i, 1, prestado + timedelta(days=14)))
    (sinteticos / "prestamos.sql").write_text(
        DDL + _insert(prestamos) + _insert(renovaciones, **RENOVACION), encoding="utf-8"
    )

    devoluciones = []
    for prestamo_id, _ in pendientes:
        if rng.random() < 0.6:
            devuelto = _instante(rng, CORTE, datetime(2031, 10, 31, tzinfo=UTC))
            devoluciones.append(
                f"update prestamo set devuelto_en = {_sql(devuelto)}, actualizado = "
                f"{_sql(devuelto)} where prestamo_id = {prestamo_id};\n"
            )
    renovadas = [
        (prestamo_id, 1, _instante(rng, CORTE, datetime(2031, 10, 31, tzinfo=UTC)))
        for prestamo_id, _ in pendientes
        if rng.random() < 0.3
    ]
    anulados = sorted(rng.sample([p for p, _ in pendientes], k=min(3, len(pendientes))))
    nuevos = []
    for i in range(len(prestamos) + 1, len(prestamos) + socios // 3 + 1):
        prestado = _instante(rng, CORTE, datetime(2031, 10, 31, tzinfo=UTC))
        nuevos.append(
            (i, rng.randint(1, socios), rng.randint(1, ejemplares), prestado, None, prestado)
        )
    (sinteticos / "prestamos_cambios.sql").write_text(
        "-- Cambios posteriores en la base de préstamos: devoluciones de préstamos pendientes,\n"
        "-- préstamos nuevos (todos con «actualizado» posterior a prestamos.sql), renovaciones\n"
        "-- nuevas y préstamos anulados, que se borran con sus renovaciones.\n"
        "-- Aplícalos con: make origen F=<carpeta>/sinteticos/prestamos_cambios.sql\n"
        + "".join(devoluciones)
        + _insert(nuevos)
        + _insert(renovadas, **RENOVACION)
        + "".join(
            f"delete from renovacion where prestamo_id = {p};\n"
            f"delete from prestamo where prestamo_id = {p};\n"
            for p in anulados
        ),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--salida", type=Path, required=True)
    ap.add_argument("--semilla", type=int, default=7)
    ap.add_argument("--socios", type=int, default=300)
    args = ap.parse_args(argv)
    generar(args.salida, args.semilla, args.socios)
    print(f"Proyecto de ejemplo en {args.salida} (semilla {args.semilla})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
