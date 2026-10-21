"""Compilador de las fórmulas de los KPI de atlantida.yml a SQL. La misma expresión sirve en
los modelos de dbt (marts_kpi, marts por actor) y en las métricas derivadas de MetricFlow: cada
KPI se define una sola vez, en el documento de definición.

Gramática admitida: identificadores de métricas base del KPI, números, + - * /, paréntesis y
max(x) de una sola métrica cuya agregación es «maximo» (ya se agrega como máximo, así que max
se omite en el SQL). Las constantes deben ser finitas. Cada división es segura y decimal:
1.0 * a / nullif(b, 0), para no dividir por cero ni truncar la división de dos enteros. Se evita
cast(… as numeric) porque MetricFlow analiza la expresión de las métricas derivadas."""

from __future__ import annotations

import ast
import math

from atlantida_def import cargar_definicion


class FormulaNoValida(ValueError):
    """La fórmula usa algo que el compilador no admite."""


_OPERADORES = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*"}


def compilar(
    formula: str, metricas: set[str], maximos: set[str] | frozenset[str] = frozenset()
) -> str:
    """«metricas»: métricas base que el KPI puede citar; «maximos»: las que se agregan como
    máximo (las únicas admitidas dentro de max)."""
    try:
        arbol = ast.parse(formula, mode="eval")
    except SyntaxError as exc:
        raise FormulaNoValida(f"fórmula con sintaxis no válida: {formula!r}") from exc
    return _sql(arbol.body, metricas, formula, maximos)


def _sql(n: ast.AST, metricas: set[str], formula: str, maximos=frozenset()) -> str:
    match n:
        case ast.BinOp(left=izq, op=ast.Div(), right=der):
            return (
                f"(1.0 * {_sql(izq, metricas, formula, maximos)} / "
                f"nullif({_sql(der, metricas, formula, maximos)}, 0))"
            )
        case ast.BinOp(left=izq, op=op, right=der) if type(op) in _OPERADORES:
            return (
                f"({_sql(izq, metricas, formula, maximos)} {_OPERADORES[type(op)]} "
                f"{_sql(der, metricas, formula, maximos)})"
            )
        case ast.Name(id=nombre) if nombre in metricas:
            return nombre
        case ast.Constant(value=v) if isinstance(v, int | float) and not isinstance(v, bool):
            if not math.isfinite(v):
                raise FormulaNoValida(f"constante no finita en {formula!r}")
            return repr(v)
        case ast.Call(func=ast.Name(id="max"), args=[ast.Name(id=nombre)], keywords=[]) if (
            nombre in metricas and nombre in maximos
        ):
            return nombre
        case ast.Call(func=ast.Name(id="max")):
            raise FormulaNoValida(
                f"max solo admite una métrica base con agregación «maximo», en {formula!r}"
            )
        case _:
            raise FormulaNoValida(f"elemento no admitido en {formula!r}: {ast.dump(n)[:80]}")


def formulas_kpi() -> dict[str, str]:
    d = cargar_definicion()
    maximos = {m.id for m in d.metricas_base if m.agregacion == "maximo"}
    return {k.id: compilar(k.formula, set(k.metricas), maximos) for k in d.kpis}
