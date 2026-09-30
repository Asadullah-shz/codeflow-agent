"""
CodeFlow Agent Evaluation Harness
Benchmarks the multi-agent pipeline across legacy code cases.
Outputs: console table + eval_report.json
"""

import asyncio
import json
import os

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
    }
    async for update in agent.run_correction_loop(prompt="", initial_code=case["code"]):
        if update.get("step") == "coding":
            result["attempts"] = max(result["attempts"], update.get("attempt", 0))
        if update.get("step") == "metrics" and result["complexity_before"] is None:
            result["complexity_before"] = (update.get("metrics_before") or {}).get("avg_complexity")
        if update.get("step") == "critic" and update.get("approved"):
            result["critic_approved"] = True
        if update.get("step") == "success":
            result["success"] = True
            result["complexity_after"] = (update.get("metrics_after") or {}).get("avg_complexity")
    return result


async def main():
    sandbox = SandboxExecutor()
    agent = CodeFlowAgent(sandbox=sandbox)

    report = []
    for case in CASES:
        print(f"\n▶ Evaluating: {case['name']}")
        r = await run_case(agent, case)
        report.append(r)
        status = "✅ PASS" if r["success"] else "❌ FAIL"
        print(f"   {status} | attempts={r['attempts']} | complexity {r['complexity_before']} → {r['complexity_after']} | critic={'✔' if r['critic_approved'] else '✘'}")

    total = len(report)
    passed = sum(1 for r in report if r["success"])
    summary = {
        "total_cases": total,
        "passed": passed,
        "success_rate_pct": round(passed / total * 100, 1),
        "avg_attempts": round(sum(r["attempts"] for r in report) / total, 2),
        "critic_approval_rate_pct": round(sum(1 for r in report if r["critic_approved"]) / total * 100, 1),
    }

    with open("eval_report.json", "w") as f:
        json.dump({"summary": summary, "cases": report}, f, indent=2)

    print("\n========== EVAL SUMMARY ==========")
    print(json.dumps(summary, indent=2))
    print("Full report saved to eval_report.json")


if __name__ == "__main__":
    asyncio.run(main())