"""AST-level mutation generator for test-strength scoring."""

import ast
import random


def generate_mutants(code: str, max_mutants: int = 6) -> list:
    tree = ast.parse(code)
    options = []

    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and type(node.op) in (ast.Add, ast.Sub):
            newop = ast.Sub() if type(node.op) is ast.Add else ast.Add()
            options.append((node.lineno, node.col_offset, type(node), "op", newop))
        elif isinstance(node, ast.Compare) and node.ops:
            repl = {
                ast.Eq: ast.NotEq, ast.NotEq: ast.Eq,
                ast.Lt: ast.LtE, ast.LtE: ast.Lt,
                ast.Gt: ast.GtE, ast.GtE: ast.Gt,
            }.get(type(node.ops[0]))
            if repl:
                options.append((node.lineno, node.col_offset, type(node), "ops", [repl()] + node.ops[1:]))
        elif isinstance(node, ast.Constant) and isinstance(node.value, int) and not isinstance(node.value, bool):
            options.append((node.lineno, node.col_offset, type(node), "value", node.value + 1))

    random.seed(42)  # deterministic = reproducible evals
    random.shuffle(options)

    mutants = []
    for lineno, col, ntype, field, val in options[:max_mutants]:
        t2 = ast.parse(code)
        target = None
        for n2 in ast.walk(t2):
            if (type(n2) is ntype
                    and getattr(n2, "lineno", None) == lineno
                    and getattr(n2, "col_offset", None) == col):
                target = n2
                break
        if target is None:
            continue
        setattr(target, field, val)
        ast.fix_missing_locations(t2)
        try:
            mutants.append(ast.unparse(t2))
        except Exception:
            continue
    return mutants