"""Behavioral invariant discovery and differential verification for CodeFlow Agent."""

import json
import re
from typing import Any, Dict, List, Tuple


INVARIANT_PROMPT = """You are a legacy-software archaeologist.
Inspect the supplied Python code and infer up to 6 concrete behavioral invariants that can be tested WITHOUT changing the code.

Return ONLY valid JSON:
{
  "invariants": [
    {
      "id": "INV-001",
      "name": "short name",
      "description": "observable behavior that should remain stable",
      "test_code": "complete pytest test body/code"
    }
  ]
}

Rules:
- Tests must use pytest and exercise public behavior.
- Prefer boundaries, empty inputs, normal inputs, error behavior, and state transitions.
- Do not invent external services or files.
- Do not assert implementation details such as helper names or exact internal structure.
- Keep each test deterministic and fast.
- The test code may import from main; the runner will normalize imports.
- Do not use network, subprocess, filesystem writes, or environment mutation.
"""


def parse_invariants(text: str) -> List[Dict[str, str]]:
    """Parse a strict JSON response while tolerating accidental code fences."""
    cleaned = re.sub(r"^\s*\`\`\`(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\`\`\`$", "", cleaned).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []

    raw = data.get("invariants", [])
    if not isinstance(raw, list):
        return []

    result: List[Dict[str, str]] = []
    for item in raw[:6]:
        if not isinstance(item, dict):
            continue
        test_code = str(item.get("test_code", "")).strip()
        if not test_code:
            continue
        result.append({
            "id": str(item.get("id", f"INV-{len(result)+1:03d}")),
            "name": str(item.get("name", "Unnamed invariant")),
            "description": str(item.get("description", "")),
            "test_code": test_code,
        })
    return result


def normalize_test_imports(test_code: str, public_names: List[str]) -> str:
    """Normalize generated invariant tests to the sandbox module."""
    if not public_names:
        return test_code
    cleaned = re.sub(r"^from\s+main\s+import.*$", "", test_code, flags=re.MULTILINE)
    cleaned = re.sub(r"^import\s+main\s*$", "", cleaned, flags=re.MULTILINE)
    return f"from main import {', '.join(public_names)}\n{cleaned.strip()}"


def public_names_from_code(code: str) -> List[str]:
    return re.findall(
        r"^(?:def|class)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\(|:)",
        code,
        re.MULTILINE,
    )


def verify_invariants(
    sandbox: Any,
    legacy_code: str,
    refactored_code: str,
    invariants: List[Dict[str, str]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Run discovered tests against both versions and identify regressions.

    An invariant is verified only when the legacy implementation passes.
    A refactor regression occurs when legacy passes but refactored fails.
    """
    legacy_names = public_names_from_code(legacy_code)
    refactored_names = public_names_from_code(refactored_code)
    verified: List[Dict[str, Any]] = []
    regressions: List[Dict[str, Any]] = []

    for inv in invariants:
        legacy_test = normalize_test_imports(inv["test_code"], legacy_names)
        refactored_test = normalize_test_imports(inv["test_code"], refactored_names)

        legacy_result = sandbox.execute(legacy_code, legacy_test)
        if not legacy_result.get("success"):
            verified.append({
                "id": inv["id"],
                "name": inv["name"],
                "description": inv["description"],
                "status": "unverified",
                "reason": "Invariant test did not pass against the legacy implementation.",
                "test_code": inv["test_code"],
                "legacy_failure": legacy_result.get("output", "")[:1200],
            })
            continue

        refactored_result = sandbox.execute(refactored_code, refactored_test)
        if refactored_result.get("success"):
            verified.append({
                "id": inv["id"],
                "name": inv["name"],
                "description": inv["description"],
                "status": "preserved",
            })
        else:
            regressions.append({
                "id": inv["id"],
                "name": inv["name"],
                "description": inv["description"],
                "status": "regression",
                "counterexample": inv["test_code"],
                "failure": refactored_result.get("output", "")[:1200],
            })

    return verified, regressions
