"""
CodeFlow Agent Phase 1 Evaluation Harness.

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
        "critic_approved": False,
        "invariants_discovered": 0,
        "invariants_preserved": 0,
        "counterexamples": 0,
        "mutation_score_pct": None,
        "security_non_regression": False,
        "proof_status": "UNKNOWN",
    }

    async for update in agent.run_correction_loop(prompt="", initial_code=case["code"]):
        if update.get("step") == "coding":
            result["attempts"] = max(result["attempts"], update.get("attempt", 0))

        if update.get("step") == "invariants":
            if update.get("invariants"):
                result["invariants_discovered"] = len(update["invariants"])
            if update.get("invariant_results"):
                result["invariants_preserved"] = sum(
                    1 for item in update["invariant_results"]
                    if item.get("status") == "preserved"
                )
            if update.get("counterexamples") is not None:
                result["counterexamples"] = len(update.get("counterexamples", []))

        if update.get("step") == "metrics" and result["complexity_before"] is None:
            result["complexity_before"] = (update.get("metrics_before") or {}).get("avg_complexity")

        if update.get("step") == "critic" and update.get("approved"):
            result["critic_approved"] = True

        if update.get("step") == "mutation" and update.get("mutation_score_pct") is not None:
            result["mutation_score_pct"] = update["mutation_score_pct"]

        if update.get("step") == "report":
            report = update.get("report", {})
            result["success"] = report.get("proof_status") == "PROVEN"
            result["proof_status"] = report.get("proof_status", "UNKNOWN")
            result["complexity_after"] = (report.get("metrics_after") or {}).get("avg_complexity")
            result["security_non_regression"] = (report.get("ship_gate") or {}).get(
                "security_non_regression", False
            )
            result["mutation_score_pct"] = (report.get("mutation") or {}).get(
                "score_pct", result["mutation_score_pct"]
            )

    return result


async def main():
    sandbox = SandboxExecutor()
    agent = CodeFlowAgent(sandbox=sandbox)

    report = []
    for case in CASES:
        print(f"\n▶ Evaluating: {case['name']}")
        r = await run_case(agent, case)
        report.append(r)
        status = "✅ PROVEN" if r["success"] else "❌ BLOCKED"
        print(
            f"   {status} | attempts={r['attempts']} | "
            f"invariants={r['invariants_preserved']}/{r['invariants_discovered']} | "
            f"counterexamples={r['counterexamples']} | "
            f"mutation={r['mutation_score_pct']}% | "
            f"security={'PASS' if r['security_non_regression'] else 'FAIL'}"
        )

    total = len(report)
    passed = sum(1 for r in report if r["success"])
    discovered = sum(r["invariants_discovered"] for r in report)
    preserved = sum(r["invariants_preserved"] for r in report)

    summary = {
        "total_cases": total,
        "proven": passed,
        "proof_rate_pct": round(passed / total * 100, 1),
        "avg_attempts": round(sum(r["attempts"] for r in report) / total, 2),
        "critic_approval_rate_pct": round(
            sum(1 for r in report if r["critic_approved"]) / total * 100, 1
        ),
        "invariants_discovered": discovered,
        "invariants_preserved": preserved,
        "invariant_preservation_pct": round(
            preserved / discovered * 100, 1
        ) if discovered else None,
        "avg_mutation_score_pct": round(
            sum((r["mutation_score_pct"] or 0) for r in report) / total, 1
        ),
        "security_non_regression_rate_pct": round(
            sum(1 for r in report if r["security_non_regression"]) / total * 100, 1
        ),
    }

    with open("eval_report.json", "w") as f:
        json.dump({"summary": summary, "cases": report}, f, indent=2)

    print("\n========== PHASE 1 EVAL SUMMARY ==========")
    print(json.dumps(summary, indent=2))
    print("Full report saved to eval_report.json")


if __name__ == "__main__":
    asyncio.run(main())
