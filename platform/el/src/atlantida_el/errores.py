"""Errores de las cargas con un mensaje que dice qué hacer."""

from __future__ import annotations


class ErrorDeCarga(RuntimeError):
    """Error previsto: la CLI muestra el mensaje sin traza."""


class PmsNoSembrado(ErrorDeCarga): ...


class SinConexion(ErrorDeCarga): ...


class DwhSinMigrar(ErrorDeCarga): ...


class CambioDeOrigen(ErrorDeCarga): ...


class ReinicioNecesario(ErrorDeCarga): ...


class TokenNoValido(ErrorDeCarga): ...


class ApiNoDisponible(ErrorDeCarga): ...


# Con ORIGEN_PMS=api y SIM_API_TOKEN vacío, el 401 se explica así (y no como «rechaza el token»).
FALTA_SIM_API_TOKEN = (
    "Falta SIM_API_TOKEN en platform/.env (el token que te da el profesor; su servidor lo pide "
    "en todas las rutas)."
)


def causa_raiz(exc: BaseException) -> BaseException:
    """dlt envuelve los errores de los recursos (PipelineStepFailed…): devuelve el original."""
    vistos: set[int] = set()
    while id(exc) not in vistos:
        vistos.add(id(exc))
        siguiente = getattr(exc, "exception", None) or exc.__cause__ or exc.__context__
        if not isinstance(siguiente, BaseException):
            break
        exc = siguiente
    return exc


def _es_autenticacion(exc: BaseException) -> bool:
    texto = str(exc).lower()
    return (getattr(exc, "sqlstate", None) or "").startswith("28") or any(
        t in texto for t in ("password", "authentication", "fe_sendauth")
    )


def error_de_conexion(destino: str, exc: BaseException, clave: str) -> SinConexion:
    """Distingue un servicio que no responde de unas credenciales rechazadas (sin mostrarlas)."""
    detalle = str(exc).splitlines()[0]
    if _es_autenticacion(exc):
        return SinConexion(
            f"{destino} rechazó el usuario o la contraseña: revisa {clave} en platform/.env. Si "
            "cambiaste esa clave con la plataforma ya creada, el rol conserva la anterior: vuelve "
            f"a poner la original, o aplica la nueva con make migrar. Detalle: {detalle}"
        )
    return SinConexion(
        f"No se puede conectar con {destino} (¿has ejecutado make up?). Detalle: {detalle}"
    )
