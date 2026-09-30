"""
CodeFlow Agent v3 — Evidence-Driven Self-Improving Refactoring Engine.

Phase 1:
- Behavioral invariant discovery and differential verification
- Concrete counterexamples for invariant regressions
- Adaptive mutation campaigns
- Evidence-backed refactoring proof and ship gate
"""

import os
import re
import json
import asyncio
import logging
from typing import List, Optional, Tuple

from openai import AsyncOpenAI
from sandbox import SandboxExecutor
from mutants import generate_mutant_cases
from invariants import INVARIANT_PROMPT, parse_invariants, verify_invariants
import memory

logger = logging.getLogger(__name__)

PRICE_PER_M = {
    "openai/gpt-oss-120b": (0.15, 0.60),
    "qwen/qwen3.8-27b": (0.10, 0.30),
}
DEFAULT_PRICE = (0.10, 0.50)

SYSTEM_PROMPT = """You are an expert Python software engineer. Your job is to:
1. Refactor the given legacy/messy Python code into clean, readable, PEP8-compliant, well-documented code.
2. Write comprehensive pytest unit tests for the refactored code.

CONTEXT:
- Your refactored code will be saved as main.py.
- Your test code will be saved as test_main.py.
- pytest will be executed from the same directory.

Return ONLY:
===REFACTORED_CODE===
(refactored Python code)
===TEST_CODE===
(pytest test code)

Rules:
1. Tests must import the exact public functions/classes defined in the refactored code.
2. Never invent a name called solution unless it exists.
3. Preserve original public function/class names whenever possible.
4. Cover edge cases and boundary values.
5. No markdown fences or prose outside the markers.
"""

CRITIC_PROMPT = """You are a strict Staff Engineer performing an adversarial production code review.
Check behavior preservation, public API compatibility, edge cases, test quality, readability, and security.

Respond ONLY with valid JSON:
{"approved": true, "feedback": "specific evidence-based feedback"}
or
{"approved": false, "feedback": "specific defect and why it matters"}
"""

INVARIANT_REPAIR_PROMPT = """You are a behavioral test archaeologist.
A candidate invariant test failed against the ORIGINAL legacy implementation. Repair only the test so it proves the stated observable behavior of the legacy code.

Return ONLY the complete pytest test code. No markdown fences or prose.

Rules:
- The test must pass against the supplied legacy implementation.
- Exercise public behavior only.
- Keep it deterministic and fast.
- Do not alter the implementation.
- Do not use network, subprocess, filesystem writes, or environment mutation.
"""

TEST_STRENGTHENER_PROMPT = """You are a test-engineering specialist.
A refactored Python implementation has surviving mutation tests. Strengthen the pytest suite so the supplied surviving mutants are detected.

Return ONLY:
===REFACTORED_CODE===
(the same implementation)
===TEST_CODE===
(a complete stronger pytest suite)

Rules:
- Preserve public behavior.
- Add targeted tests for the supplied surviving mutants.
- Prefer deterministic boundary and branch tests.
- No markdown fences or prose outside the markers.
"""


def clean_markdown(s: str) -> str:
    fence = chr(96) * 3
    s = s.replace(fence + "python", "").replace(fence, "")
    s = re.sub(r"===END===.*", "", s, flags=re.DOTALL)
    s = re.sub(r"===NOTES===.*", "", s, flags=re.DOTALL)
    s = re.sub(r"===SUMMARY===.*", "", s, flags=re.DOTALL)
    s = re.sub(r"===EXPLANATION===.*", "", s, flags=re.DOTALL)
    return s.strip()


def parse_response(text: str) -> Tuple[str, str]:
    code_match = re.search(r"===REFACTORED_CODE===(.*?)===TEST_CODE===", text, re.DOTALL)
    test_match = re.search(r"===TEST_CODE===(.*)", text, re.DOTALL)
    code = code_match.group(1).strip() if code_match else ""
    test = test_match.group(1).strip() if test_match else ""
    return clean_markdown(code), clean_markdown(test)


def parse_critic(text: str) -> Tuple[bool, str]:
    """Parse critic output with fail-closed behavior."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return False, "Critic response was missing valid JSON."
    try:
        data = json.loads(m.group(0))
    except Exception:
        return False, "Critic response contained invalid JSON."
    if not isinstance(data, dict) or "approved" not in data:
        return False, "Critic response omitted the required 'approved' field."
    return bool(data["approved"]), str(data.get("feedback", ""))


def _pick_primary_name(names: List[str], legacy_code: str) -> Optional[str]:
    if not names:
        return None
    for n in names:
        if legacy_code and re.search(rf"\b(?:def|class)\s+{re.escape(n)}\b", legacy_code):
            return n
    return names[0]


def fix_imports(refactored_code: str, test_code: str, legacy_code: str = "") -> str:
    names = re.findall(
        r"^(?:def|class)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:\(|:)",
        refactored_code,
        re.MULTILINE,
    )
    if not names:
        return test_code
    primary = _pick_primary_name(names, legacy_code)
    if primary and primary != "solution" and re.search(r"\bsolution\b", test_code):
        test_code = re.sub(r"\bsolution\b", primary, test_code)
    cleaned = re.sub(r"^from\s+main\s+import.*$", "", test_code, flags=re.MULTILINE)
    cleaned = re.sub(r"^import\s+main\s*$", "", cleaned)
    return f"from main import {', '.join(names)}\n{cleaned.strip()}"


class CodeFlowAgent:
    def __init__(self, sandbox: Optional[SandboxExecutor] = None, max_attempts: int = 3, action_queue: Optional[asyncio.Queue] = None):
        self.client = AsyncOpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )
        self.model = os.getenv("MODEL_NAME", "gpt-4o-mini")
        self.sandbox = sandbox or SandboxExecutor()
        self.max_attempts = int(os.getenv("MAX_ATTEMPTS", max_attempts))
        self.action_queue = action_queue if action_queue is not None else asyncio.Queue()

    async def _generate(self, messages: list):
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=float(os.getenv("TEMPERATURE", "0.2")),
            max_tokens=4096,
        )
        usage = getattr(response, "usage", None)
        tokens = {
            "prompt": getattr(usage, "prompt_tokens", 0) or 0,
            "completion": getattr(usage, "completion_tokens", 0) or 0,
        }
        return response.choices[0].message.content or "", tokens

    def _est_cost(self, tokens: dict) -> float:
        p_in, p_out = PRICE_PER_M.get(self.model, DEFAULT_PRICE)
        return round(tokens["prompt"] / 1_000_000 * p_in + tokens["completion"] / 1_000_000 * p_out, 6)

    async def _discover_invariants(self, initial_code: str, total_tokens: dict):
        try:
            raw, tokens = await self._generate([
                {"role": "system", "content": INVARIANT_PROMPT},
                {"role": "user", "content": f"Legacy Python code:\n\n{initial_code}"},
            ])
            total_tokens["prompt"] += tokens["prompt"]
            total_tokens["completion"] += tokens["completion"]
            return parse_invariants(raw)
        except Exception as exc:
            logger.warning("Invariant discovery failed: %s", exc)
            raise

    async def _repair_unverified_invariants(self, legacy_code: str, invariants: list, results: list, total_tokens: dict):
        repaired = []
        by_id = {item.get("id"): item for item in results if item.get("status") == "unverified"}
        for inv in invariants:
            item = by_id.get(inv.get("id"))
            if not item:
                repaired.append(inv)
                continue
            try:
                raw, tokens = await self._generate([
                    {"role": "system", "content": INVARIANT_REPAIR_PROMPT},
                    {"role": "user", "content": (
                        f"ORIGINAL LEGACY CODE:\\n{legacy_code}\\n\\n"
                        f"INVARIANT:\\n{inv.get('description','')}\\n\\n"
                        f"FAILED TEST:\\n{item.get('test_code','')}\\n\\n"
                        f"LEGACY FAILURE:\\n{item.get('legacy_failure','')}"
                    )},
                ])
                total_tokens["prompt"] += tokens["prompt"]
                total_tokens["completion"] += tokens["completion"]
                test = clean_markdown(raw)
                repaired.append({**inv, "test_code": test} if test else inv)
            except Exception as exc:
                logger.warning("Invariant probe repair failed for %s: %s", inv.get("id"), exc)
                repaired.append(inv)
        return repaired

    async def _strengthen_tests(self, refactored_code: str, test_code: str, survivors: list, total_tokens: dict):
        survivor_text = "\n".join(
            f"{m['id']} at line {m['line']}: {m['description']}" for m in survivors
        )
        try:
            raw, tokens = await self._generate([
                {"role": "system", "content": TEST_STRENGTHENER_PROMPT},
                {"role": "user", "content": (
                    f"Surviving mutants:\n{survivor_text}\n\n"
                    f"Implementation:\n{refactored_code}\n\n"
                    f"Current tests:\n{test_code}"
                )},
            ])
            total_tokens["prompt"] += tokens["prompt"]
            total_tokens["completion"] += tokens["completion"]
            new_code, new_tests = parse_response(raw)
            if new_code:
                refactored_code = new_code
            if new_tests:
                test_code = fix_imports(refactored_code, new_tests)
            return refactored_code, test_code
        except Exception as exc:
            logger.warning("Adaptive test strengthening failed: %s", exc)
            return refactored_code, test_code

    async def run_correction_loop(self, prompt: str, initial_code: str):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": (f"{prompt}\n\n" if prompt else "") + f"Legacy code to refactor:\n\n{initial_code}"},
        ]
        total_tokens = {"prompt": 0, "completion": 0}
        run_signatures = []

        yield {"step": "thinking", "attempt": 0, "message": "Starting CodeFlow Agent v3 — evidence-driven verification."}

        yield {"step": "invariants", "message": "🔎 Discovering behavioral invariants from legacy code..."}
        try:
            invariants = await self._discover_invariants(initial_code, total_tokens)
        except Exception as exc:
            logger.error("Invariant discovery API error: %s", exc)
            yield {
                "step": "error",
                "error_type": "LLM_API_ERROR",
                "message": f"❌ LLM API error during invariant discovery: {exc}",
            }
            return
        yield {
            "step": "invariants",
            "message": f"🔎 Discovered {len(invariants)} candidate behavioral invariants.",
            "invariants": [{"id": i["id"], "name": i["name"], "description": i["description"]} for i in invariants],
        }

        yield {"step": "metrics", "message": "📊 Analyzing legacy code quality (radon + pyflakes)..."}
        metrics_before = await asyncio.to_thread(self.sandbox.analyze, initial_code)
        security_before = await asyncio.to_thread(self.sandbox.security_scan, initial_code)
        yield {"step": "security", "message": f"🛡️ Legacy security scan: {security_before.get('issues', 0)} issue(s).", "security_before": security_before}
        yield {"step": "metrics", "message": f"Legacy metrics: complexity={metrics_before.get('avg_complexity')}, lint={metrics_before.get('lint_issues')}", "metrics_before": metrics_before}

        last_error = ""
        refactored_code = ""
        test_code = ""
        last_invariant_results = []
        last_regressions = []
        last_mutation_details = []

        for attempt in range(1, self.max_attempts + 1):
            if last_error:
                sig = memory.signature_of(last_error)
                lesson = memory.recall(sig)
                if lesson:
                    yield {"step": "memory", "message": f"🧠 Reflexion memory hit [{sig}]: {lesson}"}
                    last_error += f"\n\nHINT FROM PAST EXPERIENCE: {lesson}"
                messages.append({
                    "role": "user",
                    "content": f"The previous attempt FAILED on attempt {attempt - 1}.\nReason:\n{last_error}\n\nFix the issue and return the same exact format.",
                })

            yield {"step": "thinking", "attempt": attempt, "message": f"[Attempt {attempt}/{self.max_attempts}] Refactor Agent generating solution & tests..."}

            try:
                raw, tokens = await self._generate(messages)
                total_tokens["prompt"] += tokens["prompt"]
                total_tokens["completion"] += tokens["completion"]
                messages.append({"role": "assistant", "content": raw})
            except Exception as e:
                logger.error("LLM API error: %s", e)
                yield {"step": "error", "message": f"❌ LLM API error: {e}", "llm_messages": messages}
                return

            refactored_code, test_code = parse_response(raw)
            if not refactored_code:
                last_error = "Could not parse response format (missing === markers)."
                yield {"step": "failed", "attempt": attempt, "message": "⚠️ Could not parse LLM response format. Retrying...", "output": raw[:500], "llm_messages": messages}
                continue

            test_code = fix_imports(refactored_code, test_code, legacy_code=initial_code)
            yield {"step": "coding", "attempt": attempt, "message": f"[Attempt {attempt}/{self.max_attempts}] Running pytest in Docker Sandbox...", "code": refactored_code, "test_code": test_code, "llm_messages": messages}

            result = await asyncio.to_thread(self.sandbox.execute, refactored_code, test_code)
            if not result["success"]:
                sig = memory.signature_of(result["output"])
                run_signatures.append((sig, result["output"]))
                last_error = result["output"]
                yield {"step": "failed", "attempt": attempt, "message": f"⚠️ Tests failed on attempt {attempt}. Self-correcting...", "output": result["output"][:1200], "llm_messages": messages}
                continue

            metrics_after = await asyncio.to_thread(self.sandbox.analyze, refactored_code)
            yield {"step": "metrics", "message": f"Refactored metrics: complexity={metrics_after.get('avg_complexity')}, lint={metrics_after.get('lint_issues')}", "metrics_before": metrics_before, "metrics_after": metrics_after}

            if invariants:
                yield {"step": "invariants", "message": "🔬 Differentially verifying behavioral invariants..."}
                last_invariant_results, last_regressions = await asyncio.to_thread(
                    verify_invariants, self.sandbox, initial_code, refactored_code, invariants
                )
                unverified = [x for x in last_invariant_results if x.get("status") == "unverified"]
                if unverified and attempt < self.max_attempts:
                    yield {"step": "invariants", "message": f"🧪 {len(unverified)} invariant probe(s) failed on legacy behavior; repairing executable probes..."}
                    invariants = await self._repair_unverified_invariants(initial_code, invariants, last_invariant_results, total_tokens)
                    last_invariant_results, last_regressions = await asyncio.to_thread(
                        verify_invariants, self.sandbox, initial_code, refactored_code, invariants
                    )
                preserved = sum(1 for x in last_invariant_results if x.get("status") == "preserved")
                yield {
                    "step": "invariants",
                    "message": f"🔬 Behavioral proof: {preserved}/{len(invariants)} preserved; {len(last_regressions)} regression(s).",
                    "invariant_results": last_invariant_results,
                    "counterexamples": last_regressions,
                }
                if last_regressions and attempt < self.max_attempts:
                    first = last_regressions[0]
                    last_error = (
                        f"Behavioral regression detected: {first['id']} — {first['name']}.\n"
                        f"Counterexample test:\n{first['counterexample']}\n"
                        f"Failure:\n{first['failure']}"
                    )
                    continue

            yield {"step": "critic", "message": "🧑‍⚖️ Adversarial Critic reviewing the refactor..."}
            critic_messages = [
                {"role": "system", "content": CRITIC_PROMPT},
                {"role": "user", "content": (
                    f"ORIGINAL:\n{initial_code}\n\nREFACTORED:\n{refactored_code}\n\nTESTS:\n{test_code}\n\n"
                    f"METRICS BEFORE: {json.dumps(metrics_before)}\nMETRICS AFTER: {json.dumps(metrics_after)}\n"
                    f"INVARIANT EVIDENCE: {json.dumps(last_invariant_results)}\nCOUNTEREXAMPLES: {json.dumps(last_regressions)}"
                )},
            ]
            try:
                critic_raw, ctokens = await self._generate(critic_messages)
                total_tokens["prompt"] += ctokens["prompt"]
                total_tokens["completion"] += ctokens["completion"]
            except Exception:
                critic_raw = ""
            approved, feedback = parse_critic(critic_raw)
            yield {"step": "critic", "message": "✅ Critic APPROVED." if approved else "🚫 Critic REJECTED.", "critic_feedback": feedback, "approved": approved, "llm_messages": messages}
            if not approved:
                last_error = f"Code review REJECTED the refactor. Reviewer feedback:\n{feedback}"
                continue

            security_after = await asyncio.to_thread(self.sandbox.security_scan, refactored_code)
            security_scan_ok = bool(security_after.get("ok", False))
            security_regression = (
                not security_scan_ok
                or security_after.get("issues", 0) > security_before.get("issues", 0)
            )
            yield {
                "step": "security",
                "message": "🚫 Security regression detected." if security_regression else f"🛡️ Security gate passed: {security_after.get('issues', 0)} issue(s).",
                "security_before": security_before,
                "security_after": security_after,
            }
            if security_regression and attempt < self.max_attempts:
                last_error = "Security regression: refactored code has more Bandit findings than legacy code."
                continue

            yield {"step": "mutation", "message": "🧬 Running adaptive mutation campaign..."}
            mutation_cases = generate_mutant_cases(refactored_code)
            killed = 0
            survivors = []
            mutation_details = []
            for mutant in mutation_cases:
                mres = await asyncio.to_thread(self.sandbox.execute, mutant["code"], test_code)
                mutant_killed = not mres["success"]
                if mutant_killed:
                    killed += 1
                else:
                    survivors.append(mutant)
                mutation_details.append({
                    "id": mutant["id"], "line": mutant["line"], "description": mutant["description"],
                    "status": "killed" if mutant_killed else "survived",
                })
            last_mutation_details = mutation_details
            mutation_score = round(killed / len(mutation_cases) * 100, 1) if mutation_cases else 100.0
            yield {
                "step": "mutation",
                "message": f"🧬 Mutation score: {mutation_score}% ({killed}/{len(mutation_cases)} killed).",
                "mutation_score_pct": mutation_score,
                "mutation_details": mutation_details,
                "surviving_mutants": [{"id": m["id"], "line": m["line"], "description": m["description"]} for m in survivors],
            }

            if survivors and mutation_score < 80.0 and attempt < self.max_attempts:
                yield {"step": "mutation", "message": f"🧬 {len(survivors)} mutant(s) survived — generating targeted tests..."}
                refactored_code, test_code = await self._strengthen_tests(refactored_code, test_code, survivors, total_tokens)
                last_error = f"Adaptive mutation testing found {len(survivors)} surviving mutant(s); targeted tests were generated."
                continue

            invariant_regressions = len(last_regressions)
            invariant_unverified = sum(
                1 for item in last_invariant_results
                if item.get("status") == "unverified"
            )
            invariant_preserved = sum(
                1 for item in last_invariant_results
                if item.get("status") == "preserved"
            )
            invariant_gate = (
                invariant_regressions == 0
                and invariant_unverified == 0
                and invariant_preserved == len(invariants)
            )
            mutation_gate = mutation_score >= 80.0 or not mutation_cases
            ship_gate = {
                "behavioral_invariants": invariant_gate,
                "security_non_regression": security_scan_ok and not security_regression,
                "mutation_threshold": mutation_gate,
                "tests_pass": True,
            }
            proof_status = all(ship_gate.values())

            report = {
                "metrics_before": metrics_before,
                "metrics_after": metrics_after,
                "security_before": security_before,
                "security_after": security_after,
                "invariants": {
                    "discovered": len(invariants),
                    "preserved": invariant_preserved,
                    "unverified": invariant_unverified,
                    "results": last_invariant_results,
                    "counterexamples": last_regressions,
                },
                "mutation": {
                    "score_pct": mutation_score,
                    "killed": killed,
                    "total": len(mutation_cases),
                    "details": last_mutation_details,
                },
                "ship_gate": ship_gate,
                "proof_status": "PROVEN" if proof_status else "BLOCKED",
                "tokens": total_tokens,
                "est_cost_usd": self._est_cost(total_tokens),
                "attempts": attempt,
            }

            yield {
                "step": "report",
                "message": f"📜 Refactoring Proof: {report['proof_status']} | invariants={len(invariants) - invariant_regressions}/{len(invariants)} | mutation={mutation_score}% | security={'PASS' if not security_regression else 'FAIL'}",
                "report": report,
            }

            if not proof_status:
                last_error = "Evidence-backed ship gate blocked the refactor."
                continue

            yield {
                "step": "awaiting_approval",
                "message": "⏸️ Evidence-backed ship gate passed. Awaiting Human Review.",
                "code": refactored_code,
                "test_code": test_code,
                "report": report,
                "llm_messages": messages,
            }
            try:
                action_data = await asyncio.wait_for(self.action_queue.get(), timeout=300)
            except asyncio.TimeoutError:
                yield {"step": "rejected", "message": "⏱️ Timed out waiting for human approval."}
                return

            if action_data.get("action") == "approve":
                from git_utils import commit_code
                commit_msg = (
                    "refactor: evidence-backed auto-refactor "
                    f"(mutation {mutation_score}%, invariants {len(invariants) - invariant_regressions}/{len(invariants)})"
                )
                git_res = commit_code(refactored_code, test_code, commit_msg)
                yield {"step": "shipped", "message": f"🚀 {git_res}", "code": refactored_code, "test_code": test_code, "report": report, "llm_messages": messages}
                return

            yield {"step": "rejected", "message": "❌ Refactor discarded by user."}
            return

        yield {"step": "exhausted", "message": f"⛔ Agent exhausted all {self.max_attempts} attempts.", "code": refactored_code, "test_code": test_code, "output": last_error, "llm_messages": messages}
