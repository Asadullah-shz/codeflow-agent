"""AST-level mutation generator for adaptive test-strength analysis."""

import ast
import random
from typing import Any, Dict, List


def _mutation_description(field: str, old: Any, new: Any) -> str:
    if field == "op":
        return f"arithmetic operator {type(old).__name__} -> {type(new).__name__}"
    if field == "ops":
        return f"comparison operator {type(old[0]).__name__} -> {type(new[0]).__name__}"
    return f"integer constant {old!r} -> {new!r}"


def generate_mutant_cases(code: str, max_mutants: int = 6) -> List[Dict[str, Any]]:
    """Generate deterministic mutants plus machine-readable diagnostics."""
    tree = ast.parse(code)
    options = []

    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and type(node.op) in (ast.Add, ast.Sub):
            newop = ast.Sub() if type(node.op) is ast.Add else ast.Add()
            options.append({
                "lineno": node.lineno, "col_offset": node.col_offset,
                "node_type": type(node), "field": "op",
                "old": node.op, "new": newop,
                "description": _mutation_description("op", node.op, newop),
            })
        elif isinstance(node, ast.Compare) and node.ops:
            repl = {
                ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
                ast.Lt: ast.LtE, ast.LtE: ast.Lt,
                ast.Gt: ast.GtE, ast.GtE: ast.Gt,
            }.get(type(node.ops[0]))
            if repl:
                new_ops = [repl()] + node.ops[1:]
                options.append({
                    "lineno": node.lineno, "col_offset": node.col_offset,
                    "node_type": type(node), "field": "ops",
                    "old": list(node.ops), "new": new_ops,
                    "description": _mutation_description("ops", node.ops, new_ops),
                })
        elif isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
            new_value = node.value + 1
            options.append({
                "lineno": node.lineno, "col_offset": node.col_offset,
                "node_type": type(node), "field": "value",
                "old": node.value, "new": new_value,
                "description": _mutation_description("value", node.value, new_value),
            })

    random.seed(42)
    random.shuffle(options)

    mutants: List[Dict[str, Any]] = []
    for option in options[:max_mutants]:
        t2 = ast.parse(code)
        target = None
        for n2 in ast.walk(t2):
            if (
                type(n2) is option["node_type"]
                and getattr(n2, "lineno", None) == option["lineno"]
                and getattr(n2, "col_offset", None) == option["col_offset"]
            ):
                target = n2
                break
        if target is None:
            continue
        setattr(target, option["field"], option["new"])
        ast.fix_missing_locations(t2)
        try:
            mutated_code = ast.unparse(t2)
        except Exception:
            continue
        mutants.append({
            "id": f"M-{len(mutants) + 1:02d}",
            "line": option["lineno"],
            "column": option["col_offset"],
            "description": option["description"],
            "code": mutated_code,
        })
    return mutants


def generate_mutants(code: str, max_mutants: int = 6) -> list:
    """Backward-compatible API returning only mutated source strings."""
    return [m["code"] for m in generate_mutant_cases(code, max_mutants)]
