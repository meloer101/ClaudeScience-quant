from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class LiteralSite:
    value: float
    lineno: int


@dataclass(frozen=True)
class ParameterStabilityResult:
    sharpe_by_perturbation: dict[str, float]
    sharpe_spread: float
    skipped: list[str]


def find_perturbable_literals(code: str) -> list[LiteralSite]:
    tree = ast.parse(code)
    sites: list[LiteralSite] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and abs(float(node.value)) >= 2:
            sites.append(LiteralSite(value=float(node.value), lineno=getattr(node, "lineno", 0)))
    return sites


def perturb_code(code: str, factor: float) -> str:
    tree = ast.parse(code)
    transformed = _LiteralPerturber(factor).visit(tree)
    ast.fix_missing_locations(transformed)
    return ast.unparse(transformed)


def run_parameter_stability_check(
    code: str,
    rerun_with_code: Callable[[str], dict[str, float] | None],
) -> ParameterStabilityResult | None:
    if not find_perturbable_literals(code):
        return None

    values: dict[str, float] = {}
    skipped: list[str] = []
    base_metrics = rerun_with_code(code)
    if base_metrics is not None:
        values["base"] = float(base_metrics.get("sharpe", 0.0) or 0.0)
    else:
        skipped.append("base")

    for label, factor in (("-20%", 0.8), ("+20%", 1.2)):
        try:
            perturbed = perturb_code(code, factor)
            metrics = rerun_with_code(perturbed)
        except Exception:
            metrics = None
        if metrics is None:
            skipped.append(label)
            continue
        values[label] = float(metrics.get("sharpe", 0.0) or 0.0)

    if len(values) < 2:
        return ParameterStabilityResult(sharpe_by_perturbation=values, sharpe_spread=0.0, skipped=skipped)
    spread = max(values.values()) - min(values.values())
    return ParameterStabilityResult(sharpe_by_perturbation=values, sharpe_spread=float(spread), skipped=skipped)


class _LiteralPerturber(ast.NodeTransformer):
    def __init__(self, factor: float) -> None:
        self.factor = factor

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if not isinstance(node.value, (int, float)) or abs(float(node.value)) < 2:
            return node
        value = float(node.value) * self.factor
        if isinstance(node.value, int):
            value = max(2, int(round(value))) if node.value > 0 else min(-2, int(round(value)))
            return ast.copy_location(ast.Constant(value=value), node)
        return ast.copy_location(ast.Constant(value=value), node)
