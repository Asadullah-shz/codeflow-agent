"""
CodeFlow Agent v3 — Self-Improving Multi-Agent Refactoring Engine
Refactor Agent + Critic Agent + Security Auditor + Mutation Testing + Reflexion Memory
"""

import os
import re
import json
import asyncio
import logging
from typing import List, Optional, Tuple

from openai import AsyncOpenAI
from sandbox import SandboxExecutor
from mutants import generate_mutants
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
- Your refactored code will be saved as `main.py`.
- Your test code will be saved as `test_main.py`.
- `pytest` will be executed from the same directory.

You MUST return your response in this EXACT format (no markdown fences, no explanations):

===REFACTORED_CODE===
(refactored Python code, including all necessary imports)
===TEST_CODE===
(pytest test code)

STRICT RULES FOR TESTS:
1. The test file MUST import the EXACT functions/classes defined in the refactored code.
2. NEVER import a name called `solution` unless you explicitly defined `def solution` in main.py.
3. Example: if the refactored code defines `def calculate_total(items):`, the test MUST start with `from main import calculate_total`.
4. Keep the original public function names from the legacy code whenever possible.
5. No markdown fences (```), no prose outside the markers.
6. Tests MUST cover edge cases and boundary values, not just the happy path.
"""

CRITIC_PROMPT = """You are a strict Staff Engineer performing a production code review.
You will receive the original legacy code, the refactored code, its tests, and static quality metrics.

Judge whether the refactor is production-ready. Check:
1. Behavior is preserved (no unintended logic changes).
2. Readability, naming, and structure are genuinely improved.
3. Edge cases and error handling are addressed.
4. Tests are meaningful and cover the core behavior.

Respond with ONLY valid JSON in this exact shape:
{"approved": true, "feedback": "one short paragraph of specific feedback"}
or
{"approved": false, "feedback": "exactly what must be fixed and why"}
"""


def clean_markdown(s: str) -> str:
    s = re.sub(r"^```python\s*", "", s, flags=re.MULTILINE)
    s = re.sub(r"^```\s*", "", s, flags=re.MULTILINE)
    # Strip hallucinated end markers
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
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return True, "Critic response unparseable; auto-approved."
    try:
        data = json.loads(m.group(0))
        return bool(data.get("approved", True)), str(data.get("feedback", ""))
    except Exception:
        return True, "Critic response unparseable; auto-approved."


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
    cleaned = re.sub(r"^import\s+main\s*$", "", cleaned, flags=re.MULTILINE)
    correct_import = f"from main import {', '.join(names)}"
    return f"{correct_import}\n{cleaned.strip()}"


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
        return (response.choices[0].message.content or "", tokens)

    def _est_cost(self, tokens: dict) -> float:
        p_in, p_out = PRICE_PER_M.get(self.model, DEFAULT_PRICE)
        return round(tokens["prompt"] / 1_000_000 * p_in + tokens["completion"] / 1_000_000 * p_out, 6)

    async def run_correction_loop(self, prompt: str, initial_code: str):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (f"{prompt}\n\n" if prompt else "")
                + f"Legacy code to refactor:\n\n{initial_code}",
            },
        ]

        total_tokens = {"prompt": 0, "completion": 0}
        run_signatures = []

        yield {"step": "thinking", "attempt": 0, "message": "Starting CodeFlow Agent v3 (Self-Improving Multi-Agent Engine)..."}

        # --- STATIC ANALYSIS + SECURITY SCAN: BEFORE ---
        yield {"step": "metrics", "message": "📊 Analyzing legacy code quality (radon + pyflakes)..."}
        metrics_before = await asyncio.to_thread(self.sandbox.analyze, initial_code)
        security_before = await asyncio.to_thread(self.sandbox.security_scan, initial_code)
        yield {
            "step": "security",
            "message": f"🛡️ Legacy security scan: {security_before.get('issues', 0)} issue(s) found (bandit).",
            "security_before": security_before,
        }
        yield {
            "step": "metrics",
            "message": f"Legacy metrics: complexity={metrics_before.get('avg_complexity')}, lint={metrics_before.get('lint_issues')}",
            "metrics_before": metrics_before,
        }

        last_error = ""
        refactored_code = ""
        test_code = ""

        for attempt in range(1, self.max_attempts + 1):
            if last_error:
                sig = memory.signature_of(last_error)
                lesson = memory.recall(sig)
                if lesson:
                    yield {"step": "memory", "message": f"🧠 Reflexion memory hit [{sig}]: {lesson}"}
                    last_error += f"\n\nHINT FROM PAST EXPERIENCE: {lesson}"

                messages.append({
                    "role": "user",
                    "content": (
                        f"The previous attempt FAILED on attempt {attempt - 1}.\n"
                        f"Reason:\n{last_error}\n\n"
                        f"Analyze carefully, fix the issue, and return in the same exact format."
                    ),
                })

            yield {
                "step": "thinking",
                "attempt": attempt,
                "message": f"[Attempt {attempt}/{self.max_attempts}] Refactor Agent generating solution & test suite...",
            }

            try:
                raw, tokens = await self._generate(messages)
                total_tokens["prompt"] += tokens["prompt"]
                total_tokens["completion"] += tokens["completion"]
                messages.append({"role": "assistant", "content": raw})
            except Exception as e:
                logger.error(f"LLM API error: {e}")
                yield {"step": "error", "message": f"❌ LLM API error: {e}", "llm_messages": messages}
                return

            refactored_code, test_code = parse_response(raw)

            if not refactored_code:
                last_error = "Could not parse response format (missing === markers)."
                yield {
                    "step": "failed", "attempt": attempt,
                    "message": "⚠️ Could not parse LLM response format. Retrying...",
                    "output": raw[:500], "llm_messages": messages,
                }
                continue

            test_code = fix_imports(refactored_code, test_code, legacy_code=initial_code)

            yield {
                "step": "coding", "attempt": attempt,
                "message": f"[Attempt {attempt}/{self.max_attempts}] Running pytest in Docker Sandbox...",
                "code": refactored_code, "test_code": test_code, "llm_messages": messages,
            }

            result = await asyncio.to_thread(self.sandbox.execute, refactored_code, test_code)

            if result["success"]:
                metrics_after = await asyncio.to_thread(self.sandbox.analyze, refactored_code)
                yield {
                    "step": "metrics",
                    "message": f"Refactored metrics: complexity={metrics_after.get('avg_complexity')}, lint={metrics_after.get('lint_issues')}",
                    "metrics_before": metrics_before,
                    "metrics_after": metrics_after,
                }

                # --- CRITIC AGENT ---
                yield {"step": "critic", "message": "🧑‍⚖️ Critic Agent reviewing the refactor..."}
                await asyncio.sleep(1.5)  # Let Groq API rate limits cool down
                critic_messages = [
                    {"role": "system", "content": CRITIC_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"ORIGINAL LEGACY CODE:\n{initial_code}\n\n"
                            f"REFACTORED CODE:\n{refactored_code}\n\n"
                            f"TESTS:\n{test_code}\n\n"
                            f"METRICS BEFORE: {json.dumps(metrics_before)}\n"
                            f"METRICS AFTER: {json.dumps(metrics_after)}"
                        ),
                    },
                ]
                try:
                    critic_raw, ctokens = await self._generate(critic_messages)
                    total_tokens["prompt"] += ctokens["prompt"]
                    total_tokens["completion"] += ctokens["completion"]
                except Exception:
                    critic_raw = ""
                approved, feedback = parse_critic(critic_raw)

                yield {
                    "step": "critic",
                    "message": "✅ Critic Agent APPROVED the refactor." if approved else "🚫 Critic Agent REJECTED the refactor.",
                    "critic_feedback": feedback,
                    "approved": approved,
                    "llm_messages": messages,
                }

                if not approved:
                    last_error = f"Code review REJECTED the refactor. Reviewer feedback:\n{feedback}"
                    continue

                # --- SECURITY SCAN: AFTER ---
                security_after = await asyncio.to_thread(self.sandbox.security_scan, refactored_code)
                yield {
                    "step": "security",
                    "message": f"🛡️ Refactored security scan: {security_after.get('issues', 0)} issue(s).",
                    "security_before": security_before,
                    "security_after": security_after,
                }

                # --- MUTATION TESTING ---
                yield {"step": "mutation", "message": "🧬 Mutation Testing: sabotaging the code to verify test strength..."}
                mutants = generate_mutants(refactored_code)
                killed = 0
                for mcode in mutants:
                    mres = await asyncio.to_thread(self.sandbox.execute, mcode, test_code)
                    if not mres["success"]:
                        killed += 1
                mutation_score = round(killed / len(mutants) * 100, 1) if mutants else 100.0
                yield {
                    "step": "mutation",
                    "message": f"🧬 Mutation score: {mutation_score}% ({killed}/{len(mutants)} mutants killed).",
                    "mutation_score_pct": mutation_score,
                }

                if mutation_score < 50.0 and attempt < self.max_attempts:
                    last_error = (
                        f"Mutation testing scored {mutation_score}%: your tests are TOO WEAK. "
                        f"They did not detect deliberate behavior changes. "
                        f"Write stronger tests covering edge cases, boundaries, and all branches."
                    )
                    continue

                # --- STORE LESSONS IN REFLEXION MEMORY ---
                for sig, snippet in run_signatures:
                    memory.remember(sig, snippet, f"Resolved on attempt {attempt}. Critic: {feedback[:150]}")

                report = {
                    "metrics_before": metrics_before,
                    "metrics_after": metrics_after,
                    "security_before": security_before,
                    "security_after": security_after,
                    "mutation_score_pct": mutation_score,
                    "mutants_killed": killed,
                    "mutants_total": len(mutants),
                    "tokens": total_tokens,
                    "est_cost_usd": self._est_cost(total_tokens),
                    "attempts": attempt,
                }

                yield {
                    "step": "report",
                    "message": f"📈 Run report: mutation {mutation_score}% | tokens {total_tokens['prompt'] + total_tokens['completion']} | est. cost ${report['est_cost_usd']}",
                    "report": report,
                }

                # --- 🛑 HUMAN IN THE LOOP GATE ---
                yield {
                    "step": "awaiting_approval",
                    "message": "⏸️ Awaiting Human Review: Accept and commit to Git, or discard?",
                    "code": refactored_code,
                    "test_code": test_code,
                    "report": report,
                    "llm_messages": messages,
                }

                # Wait up to 5 minutes for the user to click a button in the UI
                try:
                    action_data = await asyncio.wait_for(self.action_queue.get(), timeout=300)
                except asyncio.TimeoutError:
                    yield {"step": "rejected", "message": "⏱️ Timed out waiting for human approval."}
                    return

                if action_data.get("action") == "approve":
                    from git_utils import commit_code
                    mutation_score = report.get("mutation_score_pct", "N/A")
                    commit_msg = f"refactor: auto-refactor via CodeFlow Agent (mutation score {mutation_score}%)"
                    git_res = commit_code(refactored_code, test_code, commit_msg)
                    
                    yield {
                        "step": "shipped", 
                        "message": f"🚀 {git_res}",
                        "code": refactored_code,
                        "test_code": test_code,
                        "report": report,
                        "llm_messages": messages,
                    }
                    return
                else:
                    yield {"step": "rejected", "message": "❌ Refactor discarded by user."}
                    return

            sig = memory.signature_of(result["output"])
            run_signatures.append((sig, result["output"]))
            last_error = result["output"]
            yield {
                "step": "failed", "attempt": attempt,
                "message": f"⚠️ Tests failed on attempt {attempt}. Self-correcting...",
                "output": result["output"][:800], "llm_messages": messages,
            }

        yield {
            "step": "exhausted",
            "message": f"⛔ Agent exhausted all {self.max_attempts} attempts.",
            "code": refactored_code, "test_code": test_code,
            "output": last_error, "llm_messages": messages,
        }