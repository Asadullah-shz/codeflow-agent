"""Unit tests for CodeFlow Agent Phase 1 primitives."""

from invariants import parse_invariants, normalize_test_imports, public_names_from_code
from mutants import generate_mutant_cases


def test_parse_invariants_accepts_json():
    payload = '{"invariants":[{"id":"INV-001","name":"positive input","description":"preserves output","test_code":"def test_x():\\n    assert True"}]}'
    result = parse_invariants(payload)
    assert len(result) == 1
    assert result[0]["id"] == "INV-001"


def test_parse_invariants_rejects_invalid_json():
    assert parse_invariants("not json") == []


def test_public_names_and_import_normalization():
    code = "def calculate_total(items):\n    return sum(items)\n"
    names = public_names_from_code(code)
    assert names == ["calculate_total"]

    test_code = "from main import wrong\n\ndef test_total():\n    assert calculate_total([1, 2]) == 3\n"
    normalized = normalize_test_imports(test_code, names)
    assert normalized.startswith("from main import calculate_total")
    assert "from main import wrong" not in normalized


def test_mutation_generation_is_deterministic_and_structured():
    code = "def calculate(a, b):\n    return a + b\n"
    first = generate_mutant_cases(code)
    second = generate_mutant_cases(code)
    assert first == second
    assert first
    assert {"id", "line", "column", "description", "code"} <= set(first[0])


def test_mutation_description_identifies_operator_change():
    code = "def calculate(a, b):\n    return a + b\n"
    mutants = generate_mutant_cases(code)
    assert any("Add" in m["description"] and "Sub" in m["description"] for m in mutants)


def test_unverified_invariant_keeps_executable_probe_evidence():
    from invariants import verify_invariants

    class FakeSandbox:
        def __init__(self):
            self.calls = []

        def execute(self, code, test_code):
            self.calls.append(test_code)
            return {"success": False, "output": "legacy probe failed"}

    sandbox = FakeSandbox()
    invariants = [{
        "id": "INV-001",
        "name": "boundary",
        "description": "boundary behavior",
        "test_code": "def test_boundary():\n    assert True",
    }]
    results, regressions = verify_invariants(sandbox, "def calc(x): return x", "def calc(x): return x", invariants)

    assert regressions == []
    assert results[0]["status"] == "unverified"
    assert results[0]["test_code"] == invariants[0]["test_code"]
    assert results[0]["legacy_failure"] == "legacy probe failed"
