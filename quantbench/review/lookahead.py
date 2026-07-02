from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class LookaheadIssue:
    pattern: str
    detail: str
    line: int | None


_NEGATIVE_PERIOD_METHODS = {"shift", "diff", "pct_change"}
_GLOBAL_AGGREGATES = {"mean", "median", "std", "var", "min", "max", "sum"}


def detect_lookahead(code: str) -> list[LookaheadIssue]:
    """Detect high-confidence lookahead patterns in generated factor code."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return [LookaheadIssue("syntax_error", f"Code could not be parsed: {exc}", exc.lineno)]

    visitor = _LookaheadVisitor(code)
    visitor.visit(tree)
    return visitor.issues


class _LookaheadVisitor(ast.NodeVisitor):
    def __init__(self, code: str) -> None:
        self.code = code
        self.issues: list[LookaheadIssue] = []

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            name = node.func.attr
            if name in _NEGATIVE_PERIOD_METHODS and _first_numeric_arg_is_negative(node):
                self._add("negative_period", node, f".{name}() called with a negative period")
            if name in _GLOBAL_AGGREGATES and not _has_windowed_parent(node.func.value):
                self._add("unwindowed_full_column_aggregate", node, f".{name}() used without rolling/expanding window")
            if _is_iloc_attr(node.func.value) and _first_numeric_arg_is_negative(node):
                self._add("iloc_negative_index", node, ".iloc called with a negative index")

        if _is_np_roll(node) and _np_roll_shift_is_negative(node):
            self._add("negative_np_roll", node, "np.roll called with a negative shift")

        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if isinstance(node.slice, ast.Slice) and _numeric_value(node.slice.step) == -1:
            self._add("reverse_slice", node, "Reverse slice with step -1 can invert time order")
        if _is_iloc_attr(node.value):
            value = _subscript_value(node.slice)
            if value == -1:
                self._add("iloc_last_row", node, ".iloc[-1] reads the final row of the full sample")
            elif value is not None and value > 0:
                self._add("iloc_forward_row", node, f".iloc[{value:g}] reads a fixed future row in early periods")
        self.generic_visit(node)

    def _add(self, pattern: str, node: ast.AST, message: str) -> None:
        snippet = ast.get_source_segment(self.code, node) or type(node).__name__
        self.issues.append(
            LookaheadIssue(
                pattern=pattern,
                detail=f"{message}: {snippet}",
                line=getattr(node, "lineno", None),
            )
        )


def _first_numeric_arg_is_negative(node: ast.Call) -> bool:
    if node.args:
        value = _numeric_value(node.args[0])
        return value is not None and value < 0
    for keyword in node.keywords:
        if keyword.arg in {"periods", "shift", "period"}:
            value = _numeric_value(keyword.value)
            return value is not None and value < 0
    return False


def _np_roll_shift_is_negative(node: ast.Call) -> bool:
    if len(node.args) >= 2:
        value = _numeric_value(node.args[1])
        return value is not None and value < 0
    for keyword in node.keywords:
        if keyword.arg == "shift":
            value = _numeric_value(keyword.value)
            return value is not None and value < 0
    return False


def _is_np_roll(node: ast.Call) -> bool:
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "roll"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "np"
    )


def _is_iloc_attr(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "iloc"


def _has_windowed_parent(node: ast.AST) -> bool:
    current = node
    while isinstance(current, ast.Call) and isinstance(current.func, ast.Attribute):
        if current.func.attr in {"rolling", "expanding", "ewm", "groupby", "resample"}:
            return True
        current = current.func.value
    while isinstance(current, ast.Attribute):
        if current.attr in {"rolling", "expanding", "ewm"}:
            return True
        current = current.value
    return False


def _subscript_value(slice_node: ast.AST) -> float | None:
    if isinstance(slice_node, ast.Tuple):
        return None
    return _numeric_value(slice_node)


def _numeric_value(node: ast.AST | None) -> float | None:
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _numeric_value(node.operand)
        return -value if value is not None else None
    return None
