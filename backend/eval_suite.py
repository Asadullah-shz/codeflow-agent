"""
CodeFlow Agent Phase 1.2 Evaluation Harness.

Evaluates behavioral proof, counterexamples, adaptive mutation testing,
security non-regression, and the evidence-backed ship gate.
"""

import asyncio
import json

from dotenv import load_dotenv
from agent import CodeFlowAgent
from sandbox import SandboxExecutor

load_dotenv()

CASES = [
    {
        "name": "nested_calculator",
        "code": 'def calc(a,b,c):\n    if c=="+":\n        return a+b\n    elif c=="-":\n        return a-b\n    elif c=="*":\n        return a*b\n    elif c=="/":\n        if b==0:\n            return "err"\n        return a/b\n    else:\n        return "nope"',
    },
    {
        "name": "palindrome_edge_cases",
        "code": "def check_palindrome(text):\n    return text == text[::-1]",
    },
    {
        "name": "messy_class",
        "code": "class user_mgr:\n    def __init__(self):\n        self.usrs = []\n    def add_usr(self, name, age):\n        self.usrs.append({'n': name, 'a': age})\n    def get_adults(self):\n        res = []\n        for u in self.usrs:\n            if u['a'] >= 18:\n                res.append(u['n'])\n        return res",
    },
    {
        "name": "mutable_default_bug",
        "code": "def add_item(item, lst=[]):\n    lst.append(item)\n    return lst",
    },
    {
        "name": "string_builder",
        "code": "def build_report(items):\n    out = ''\n    for i in items:\n        out = out + str(i) + '\\n'\n    return out",
    },
]


async def run_case(agent: CodeFlowAgent, case: dict) -> dict:
    result = {
        "name": case["name"],
        "success": False,
        "attempts": 0,
        "complexity_before": None,
        "complexity_after": None,
        "critic_status": "NOT_RUN",
        "invariants_discovered": 0,
        "invariants_preserved": 0,
        "invariants_unverified": 0,
        "invariant_status": "NOT_RUN",
        "counterexamples": 0,
        "mutation_status": "NOT_RUN",
        "mutation_score_pct": None,
        "security_status": "NOT_RUN",
        "proof_status": "UNKNOWN",
        "termination": "UNKNOWN",
        "error_type": None,
        "error_message": None,
    }

    async for update in agent.run_correction_loop(prompt="", initial_code=case["code"]):
        if update.get("step") == "error":
            message = str(update.get("message", "LLM API error"))
            result["error_type"] = "LLM_API_ERROR"
            result["error_message"] = message[:500]
            result["termination"] = "API_ERROR"
            continue
        if update.get("step") == "coding":
            result["attempts"] = max(result["attempts"], update.get("attempt", 0))

        if update.get("step") == "invariants":
            if "invariants" in update:
                result["invariants_discovered"] = len(update.get("invariants") or [])
            if "invariant_results" in update:
                items = update.get("invariant_results") or []
                regressions = update.get("counterexamples") or []
                result["invariants_preserved"] = sum(1 for item in items if item.get("status") == "preserved")
                result["invariants_unverified"] = sum(1 for item in items if item.get("status") == "unverified")
                result["counterexamples"] = len(regressions)
                if regressions:
                    result["invariant_status"] = "FAIL"
                elif not items:
                    result["invariant_status"] = "NOT_RUN"
                elif result["invariants_unverified"]:
                    result["invariant_status"] = "PARTIAL"
                elif result["invariants_preserved"] == result["invariants_discovered"]:
                    result["invariant_status"] = "PASS"
                else:
                    result["invariant_status"] = "PARTIAL"

        if update.get("step") == "metrics" and result["complexity_before"] is None:
            result["complexity_before"] = (update.get("metrics_before") or {}).get("avg_complexity")

        if update.get("step") == "critic" and "approved" in update:
            result["critic_status"] = "PASS" if update["approved"] else "FAIL"

        if update.get("step") == "mutation" and update.get("mutation_score_pct") is not None:
            result["mutation_score_pct"] = update["mutation_score_pct"]
            result["mutation_status"] = "PASS" if update["mutation_score_pct"] >= 80.0 else "FAIL"

        if update.get("step") == "report":
            report = update.get("report", {})
            gate = report.get("ship_gate") or {}
            mutation = report.get("mutation") or {}
            result["success"] = report.get("proof_status") == "PROVEN"
            result["proof_status"] = report.get("proof_status", "UNKNOWN")
            result["termination"] = "PROVEN" if result["success"] else "BLOCKED"
            result["complexity_after"] = (report.get("metrics_after") or {}).get("avg_complexity")
            result["security_status"] = "PASS" if gate.get("security_non_regression") else "FAIL"
            if mutation.get("score_pct") is not None:
                result["mutation_score_pct"] = mutation["score_pct"]
                result["mutation_status"] = "PASS" if mutation["score_pct"] >= 80.0 else "FAIL"

    if result["termination"] == "UNKNOWN":
        result["termination"] = "EXHAUSTED"
    return result


async def main():
    sandbox = SandboxExecutor()
    agent = CodeFlowAgent(sandbox=sandbox)
    report = []

    for case in CASES:
        print(f"\n▶ Evaluating: {case['name']}")
        r = await run_case(agent, case)
        report.append(r)
        mutation = f"{r['mutation_score_pct']}%" if r["mutation_status"] != "NOT_RUN" else "NOT_RUN"
        status = "PROVEN" if r["success"] else r["termination"]
        print(
            f"   {'✅' if r['success'] else '❌'} {status} | attempts={r['attempts']} | "
            f"invariants={r['invariants_preserved']}/{r['invariants_discovered']} ({r['invariant_status']}) | "
            f"counterexamples={r['counterexamples']} | mutation={mutation} ({r['mutation_status']}) | "
            f"security={r['security_status']} | critic={r['critic_status']}"
        )

    total = len(report)
    proven = sum(r["success"] for r in report)
    discovered = sum(r["invariants_discovered"] for r in report)
    preserved = sum(r["invariants_preserved"] for r in report)
    mutation_scores = [r["mutation_score_pct"] for r in report if r["mutation_status"] != "NOT_RUN"]
    security_evaluated = [r for r in report if r["security_status"] != "NOT_RUN"]

    summary = {
        "total_cases": total,
        "proven": proven,
        "proof_rate_pct": round(proven / total * 100, 1) if total else None,
        "avg_attempts": round(sum(r["attempts"] for r in report) / total, 2) if total else None,
        "critic": {k: sum(r["critic_status"] == k for r in report) for k in ["PASS", "FAIL", "NOT_RUN"]},
        "invariants": {
            "discovered": discovered,
            "preserved": preserved,
            "unverified": sum(r["invariants_unverified"] for r in report),
            "preservation_pct": round(preserved / discovered * 100, 1) if discovered else None,
            "verification_status": {k: sum(r["invariant_status"] == k for r in report) for k in ["PASS", "FAIL", "PARTIAL", "NOT_RUN"]},
        },
        "mutation": {
            "evaluated_cases": len(mutation_scores),
            "not_run_cases": sum(r["mutation_status"] == "NOT_RUN" for r in report),
            "passed_cases": sum(r["mutation_status"] == "PASS" for r in report),
            "failed_cases": sum(r["mutation_status"] == "FAIL" for r in report),
            "avg_score_pct": round(sum(mutation_scores) / len(mutation_scores), 1) if mutation_scores else None,
        },
        "security": {
            "evaluated_cases": len(security_evaluated),
            "not_run_cases": sum(r["security_status"] == "NOT_RUN" for r in report),
            "passed_cases": sum(r["security_status"] == "PASS" for r in report),
            "failed_cases": sum(r["security_status"] == "FAIL" for r in report),
            "pass_rate_pct": round(sum(r["security_status"] == "PASS" for r in security_evaluated) / len(security_evaluated) * 100, 1) if security_evaluated else None,
        },
        "termination": {k: sum(r["termination"] == k for r in report) for k in ["PROVEN", "BLOCKED", "EXHAUSTED", "API_ERROR"]},
        "api_errors": {
            "cases": sum(r["termination"] == "API_ERROR" for r in report),
            "error_types": {
                k: sum(r["error_type"] == k for r in report)
                for k in sorted({r["error_type"] for r in report if r["error_type"]})
            },
        },
    }

    with open("eval_report.json", "w") as f:
        json.dump({"phase": "1.2", "summary": summary, "cases": report}, f, indent=2)

    print("\n========== PHASE 1.2 EVAL SUMMARY ==========")
    print(json.dumps(summary, indent=2))
    print("Full report saved to eval_report.json")

if __name__ == "__main__":
    asyncio.run(main())
