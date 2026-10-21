"""Huella de la sal de los seudónimos (DWH_SEUDONIMO_SAL).

Cambiar la sal cambia todos los seudónimos: las fichas ya guardadas en el almacén (snapshot de
huéspedes, satélite del vault) conservarían los de la sal anterior. Para no mezclar dos sales en
silencio, la última construcción guarda en meta.carga la huella de la sal (nunca la sal) y la
siguiente se niega a seguir si ha cambiado. Una huella de SHA-256 no permite recuperar la sal."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence

from atlantida_el import meta
from atlantida_el.errores import ErrorDeCarga, ReinicioNecesario

FUENTE_SAL = "sal"
SALES_DE_EJEMPLO = ("sal_de_desarrollo", "sal_de_desarrollo_cambiala")  # dbt las trata como una


ORDENES_CON_SAL = frozenset({"build", "run", "snapshot", "retry"})
_FORMATO = re.compile(r"[A-Za-z0-9_-]{8,}")


class SalNoValida(ErrorDeCarga):
    """Sal vacía, de ejemplo (fuera de CI) o con caracteres que no caben en la conexión."""


class SalCambiada(ReinicioNecesario):
    """La sal de los seudónimos no es la de la última construcción del almacén."""


def efectiva(entorno: Mapping[str, str]) -> str:
    """La sal con la que se construye: la de .env; en CI, sin sal, la de desarrollo."""
    valor = entorno.get("DWH_SEUDONIMO_SAL", "")
    if valor in ("", *SALES_DE_EJEMPLO):
        if entorno.get("CI"):
            return "sal_de_desarrollo"
        raise SalNoValida(
            "DWH_SEUDONIMO_SAL está vacía o tiene un valor de ejemplo público: deja la línea vacía "
            "en platform/.env (DWH_SEUDONIMO_SAL=) y ejecuta make up, que genera una sal secreta."
        )
    if not _FORMATO.fullmatch(valor):
        raise SalNoValida(
            "DWH_SEUDONIMO_SAL solo admite letras sin tilde, dígitos, «_» y «-» (al menos 8): "
            "viaja en la conexión al DWH. Deja la línea vacía y make generará una válida (ojo: "
            "cambiar la sal obliga a reconstruir, ver make pipeline REINICIAR=1)."
        )
    return valor


def _opciones_pg(sal: str, entorno: Mapping[str, str]) -> str:
    """Opciones de sesión de libpq (PGOPTIONS): dbt-postgres no admite `options` en el perfil."""
    limite = entorno.get("DBT_STATEMENT_TIMEOUT_MS", "") or "600000"
    if not limite.isdigit():
        raise ErrorDeCarga(
            "DBT_STATEMENT_TIMEOUT_MS debe ser un número de milisegundos (0: sin límite)."
        )
    return f"-c statement_timeout={limite} -c atlantida.sal={sal}"


def para_dbt(entorno: Mapping[str, str]) -> dict[str, str]:
    """Variables para lanzar dbt. La sal llega a cada conexión como parámetro de sesión
    atlantida.sal por PGOPTIONS (libpq), nunca en el SQL. DBT_ENV_SECRET_SAL lleva el mismo
    valor para que dbt lo borre de cualquier mensaje que fuera a registrar."""
    valor = efectiva(entorno)
    return {"DBT_ENV_SECRET_SAL": valor, "PGOPTIONS": _opciones_pg(valor, entorno)}


def para_dbt_segun(args: Sequence[str], entorno: Mapping[str, str]) -> dict[str, str]:
    """Las órdenes que construyen exigen una sal válida; las demás (ls, parse, compile, docs…)
    no seudonimizan nada y funcionan aunque falte."""
    try:
        return para_dbt(entorno)
    except SalNoValida:
        if args and args[0] in ORDENES_CON_SAL:
            raise
        return {"DBT_ENV_SECRET_SAL": "sin_sal", "PGOPTIONS": _opciones_pg("sin_sal", entorno)}


def huella(sal: str) -> str:
    sal = "sal_de_desarrollo" if sal in SALES_DE_EJEMPLO else sal
    return hashlib.sha256(f"atlantida-sal:{sal}".encode()).hexdigest()[:16]


def _guardada(url_dwh: str) -> str | None:
    with meta._conectar(url_dwh) as c:
        fila = c.execute(
            "select detalle->>'huella' from meta.carga where fuente = %s and estado = 'ok' "
            "order by id desc limit 1",
            (FUENTE_SAL,),
        ).fetchone()
    return fila[0] if fila else None


def comprobar(url_dwh: str, entorno: Mapping[str, str], reiniciar: bool = False) -> bool:
    """True si la sal ha cambiado y se acepta porque se reinicia (hay que rehacer las fichas).
    Sin huella guardada o con una sal vacía o de ejemplo no hay nada que comparar."""
    sal = entorno.get("DWH_SEUDONIMO_SAL", "")
    previa = _guardada(url_dwh) if sal else None  # sin sal, dbt se detiene con su propio mensaje
    if previa is None or previa == huella(sal):
        return False
    if reiniciar:
        return True
    raise SalCambiada(
        "La sal de los seudónimos (DWH_SEUDONIMO_SAL) no es la de la última construcción del "
        "almacén: el snapshot de huéspedes y el satélite del vault mezclarían seudónimos de dos "
        "sales. Si fue un error, vuelve a poner la sal anterior en platform/.env (no borres el "
        "fichero). Si la cambiaste a propósito, empieza de cero con make pipeline REINICIAR=1 "
        "(rehace esas fichas con la sal nueva) o con make historico."
    )


def registrar(url_dwh: str, entorno: Mapping[str, str]) -> None:
    """Guarda la huella de la sal usada (si cambió o no había ninguna)."""
    sal = entorno.get("DWH_SEUDONIMO_SAL", "")
    if not sal:
        return
    actual = huella(sal)
    if _guardada(url_dwh) == actual:
        return
    marca = meta.abrir(url_dwh, FUENTE_SAL, "seudonimos")
    meta.cerrar(url_dwh, marca, "ok", None, {"huella": actual})
