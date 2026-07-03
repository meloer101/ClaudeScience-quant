from __future__ import annotations

import ast


def extract_compute_source(source: str) -> str:
    """Pull just the `def compute(...)` function body out of a run's
    signal.py (which also carries SIGNAL_FILE_HEADER/HARNESS boilerplate).

    Shared by quantbench/factors/entry.py (saving a run into the Factor
    Library) and quantbench/monitor/pipeline.py (re-executing a run's factor
    against fresh data for decay checks) so the AST parsing rule for "what
    counts as the factor's code" lives in exactly one place.
    """
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "compute":
            segment = ast.get_source_segment(source, node)
            if segment:
                return segment.rstrip() + "\n"
    raise ValueError("signal.py must define def compute(...)")
