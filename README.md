<div align="center">

# 🤖 CodeFlow Agent v3

### A self-improving multi-agent engine that refactors legacy code, proves correctness in an isolated Docker sandbox, survives adversarial review — and learns from its own failures.

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-14-000000?style=for-the-badge&logo=nextdotjs&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Sandbox-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?style=for-the-badge&logo=typescript&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

**[🎥 Demo Video](#)** · **[📊 Eval Report](backend/eval_report.json)** · **[ Live Demo](#)**

</div>

---

## 🎯 The Problem

Most AI coding tools **generate code and hope it works**. They hallucinate imports, skip edge cases, write weak tests, and silently ship vulnerabilities. In production systems, "hopefully correct" is not acceptable.

**CodeFlow Agent takes responsibility for correctness.** It doesn't just rewrite code — it *proves* the rewrite is better, safer, and better-tested than the original, using deterministic engineering guardrails around non-deterministic LLMs.

---

## ✨ What Makes This Different

| Typical "AI Code Tool" | CodeFlow Agent v3 |
|---|---|
| Single LLM call, no verification | **7-stage agentic pipeline** with verification at every step |
| Trusts the model's output | Executes generated tests in a **network-isolated Docker sandbox** |
| No quality proof | **Mutation testing** sabotages the code to score test strength |
| Ignores security | **Bandit security audits** before & after refactoring |
| Stateless | **Reflexion episodic memory** — learns from past failures across sessions |
| Black box | **Full LLM observability** — every prompt/response streamed to a Trace Inspector |
| Fully autonomous (dangerous) | **Human-in-the-loop gate** — engineers hold final commit authority |

---

## 🏗️ Architecture

```
┌──────────────────────────  NEXT.JS MISSION-CONTROL UI  ──────────────────────────┐
│  Pipeline Graph · Live Agent Terminal · Code Diff · Quality Metrics · LLM Trace  │
└───────────────────────────────────▲──────────────────────────────────────────────┘
                                    │ WebSocket (real-time streaming)
┌───────────────────────────────────▼──────────────────────────────────────────────┐
│                            FASTAPI ORCHESTRATOR                                  │
│                                                                                  │
│   ┌───────────────┐    ┌──────────────────────────────────────────────────────┐  │
│   │ 📥 Legacy Code │───►│  REFACTOR AGENT (LLM)                                │  │
│   └───────────────┘    │  generates refactor + pytest suite                   │  │
│                        └───────────────▲──────────────────────────────────────┘  │
│                                        │ error feedback / critic rejection       │
│   ┌────────────────────────────────────┴─────────────────────────────────────┐   │
│   │                    🐳 DOCKER SANDBOX (network-disabled)                  │   │
│   │   pytest execution · radon complexity · pyflakes lint · bandit security  │   │
│   │   🧬 mutation engine (AST-level sabotage → test strength score)          │   │
│   └────────────────────────────────────┬─────────────────────────────────────┘   │
│                                        ▼                                         │
│   ┌──────────────────┐   ┌──────────────────┐   ┌────────────────────────────┐   │
│   │ 🧑‍⚖️ CRITIC AGENT  │   │ 🧠 REFLEXION      │   │ 🛑 HUMAN-IN-THE-LOOP GATE  │   │
│   │ adversarial review│   │ MEMORY (SQLite)  │   │ approve → git commit       │   │
│   │ can REJECT refactor│  │ learns failures  │   │ reject  → discard          │   │
│   └──────────────────┘   └──────────────────┘   └────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔬 The 7-Stage Pipeline

1. **📊 Analyze** — `radon` (cyclomatic complexity) + `pyflakes` (lint) + `bandit` (security) baseline the legacy code inside the sandbox.
2. **✍️ Refactor** — The Refactor Agent generates PEP8-clean code + a pytest suite under a strict output contract.
3. **🐳 Test** — Code + tests execute in an ephemeral, **network-disabled, memory-capped** Docker container. On failure, the agent reads its own `stderr` and self-corrects.
4. **🧑‍⚖️ Critic** — An adversarial Staff-Engineer agent reviews behavior preservation, readability, and test quality. It can **reject** the refactor and force another attempt.
5. **🛡️ Security** — Bandit re-scans the refactored code; vulnerabilities must not increase.
6. **🧬 Mutants** — The mutation engine applies AST-level sabotage (`+`→`-`, `==`→`!=`, constants+1). Tests that fail to kill mutants are flagged as weak and the agent is forced to strengthen them.
7. **🛑 Ship** — A human reviewer accepts or discards. On acceptance, the code is committed to a local Git repository with an auto-generated commit message.

---

## 📊 Evaluation Results

Benchmarked with the built-in evaluation harness (`eval_suite.py`) across 5 adversarial legacy-code cases (nested conditionals, edge-case traps, mutable-default bugs, class refactors):

| Metric | Result |
|---|---|
| **Success Rate** | **100.0%** (5/5 cases) |
| **Avg Attempts to Resolution** | **1.8** |
| **Critic Approval Rate** | **100.0%** |
| **Sandbox** | Network-isolated, 256MB-capped ephemeral containers |

Reproduce locally:
```bash
cd backend && python eval_suite.py   # writes eval_report.json
```

---

## 🧠 Key Engineering Decisions

### 1. Deterministic Guardrails Around Non-Deterministic Models
LLMs trained on LeetCode-style data hallucinate `from main import solution`. Instead of praying for better prompts, an **AST/regex guardrail layer** rewrites test imports to match exactly what exists in the generated module — converting a stochastic failure mode into a solved engineering problem.

### 2. Mutation Testing as a Test-Quality Oracle
Passing tests prove nothing if they're weak. By injecting AST-level mutants and measuring the **kill rate**, the system quantifies test strength and rejects suites scoring below threshold.

### 3. Reflexion-Style Episodic Memory
Failure signatures (e.g., `AssertionError`, `ImportError`) and their resolutions are persisted to SQLite. On future runs, similar failures trigger **memory recall**, injecting past lessons into the self-correction prompt — the agent improves across sessions.

### 4. Security-First Sandboxing
AI-generated code is untrusted code. Every execution happens in an ephemeral container with **no network access**, memory caps, and automatic cleanup.

### 5. Human-in-the-Loop by Design
Autonomy without authority. The pipeline pauses at a review gate; only a human click produces a Git commit. AI proposes — engineers dispose.

### 6. Full Observability & Run Economics
Every prompt, response, token count, and estimated cost is streamed to the UI Trace Inspector — because production AI systems must be debuggable, not magical.

---

## 🛠️ Tech Stack

**Backend:** Python 3.11 · FastAPI · WebSockets · Docker SDK · OpenAI-compatible APIs (Groq / OpenAI / Ollama) · SQLite · radon · pyflakes · bandit · pytest

**Frontend:** Next.js 14 (App Router) · TypeScript · Tailwind CSS · WebSockets · react-diff-viewer · Prism.js

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+, Node.js 18+, **Docker Desktop running**, Git
- An OpenAI-compatible API key (Groq free tier recommended) or local Ollama

### 1. Backend
```bash
cd backend
python -m venv venv
venv\Scripts\activate        # Windows  (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt

# Build the sandbox image (one-time, ~60s)
docker build -f Dockerfile.sandbox -t codeflow-sandbox:latest .

# Configure
cp .env.example .env         # then add your API key (see table below)

python main.py               # → http://localhost:8000
```

### 2. Frontend
```bash
cd frontend
npm install
npm run dev                  # → http://localhost:3000
```

### Environment Variables (`backend/.env`)

| Variable | Description | Example |
|---|---|---|
| `OPENAI_API_KEY` | Any OpenAI-compatible key | `gsk_...` / `AIza...` / `ollama` |
| `OPENAI_BASE_URL` | Provider endpoint | `https://api.groq.com/openai/v1` |
| `MODEL_NAME` | Chat model ID | `openai/gpt-oss-120b` |
| `MAX_ATTEMPTS` | Self-correction budget | `3` |
| `TEMPERATURE` | Sampling temperature | `0.2` |

> Provider-agnostic by design: swap Groq ↔ OpenAI ↔ Google Gemini ↔ local Ollama with **zero code changes**.

---

## 📁 Project Structure

```
codeflow-agent/
├── backend/
│   ├── main.py            # FastAPI + WebSocket orchestrator
│   ├── agent.py           # Multi-agent loop (Refactor + Critic + memory)
│   ├── sandbox.py         # Docker sandbox: pytest, radon, pyflakes, bandit
│   ├── mutants.py         # AST-level mutation engine
│   ├── memory.py          # Reflexion episodic memory (SQLite)
│   ├── git_utils.py       # Human-approved Git commits
│   ├── eval_suite.py      # Benchmark harness → eval_report.json
│   └── Dockerfile.sandbox # Pre-baked sandbox image
└── frontend/
    ├── app/               # Next.js App Router
    ├── components/        # PipelineGraph, AgentTerminal, DiffViewer,
    │                      # MetricsPanel, AgentTrace, CodeEditor
    └── hooks/             # useWebSocket (real-time agent streaming)
```

---

## 🗺️ Future Ideas (Deliberately Deferred)

- Multi-language support (TS/Java) via tree-sitter
- Real GitHub PR ingestion as evaluation cases
- VS Code extension wrapper
- Side-by-side model comparison runs (GPT-OSS vs Qwen vs Llama)
- Parallel sandbox execution for large-scale evals

*Deferred intentionally to ship v3. Revisit after launch feedback.*

---

## 🤝 Author

Built by **[Asadullah Shahbaz](https://github.com/AsadullahShahbaz)** — Full-Stack Developer transitioning into AI Engineering.
[LinkedIn](YOUR_LINKEDIN_URL) · Open to AI Engineer / LLM Application Engineer roles.

## 📄 License

MIT — free to use, fork, and learn from.

## Phase 1 — Evidence-Driven Verification

CodeFlow Agent now goes beyond pass/fail testing with an evidence-oriented verification layer:

- **Behavioral Invariant Discovery** — the agent first asks a dedicated legacy-code archaeologist to identify observable behaviors worth preserving.
- **Differential Invariant Verification** — discovered tests are executed against both the legacy and refactored implementations. A behavior that passes in the legacy version but fails after refactoring becomes a concrete regression.
- **Counterexamples** — invariant regressions retain the exact failing test and sandbox output so the next agent attempt receives a concrete failure case instead of a vague critique.
- **Adaptive Mutation Testing** — mutation results now identify the surviving mutant, source location, and mutation type. Surviving mutants trigger a targeted test-strengthening pass before another verification attempt.
- **Evidence-Backed Refactoring Proof** — the final report records invariant preservation, security non-regression, mutation score, test success, and an explicit ship gate.
- **Human approval remains mandatory** — passing automated evidence does not automatically authorize the Git commit.

### Phase 1 Verification Flow

```
Legacy Code
    ↓
Invariant Discovery
    ↓
AI Refactor + Tests
    ↓
Isolated Sandbox
    ↓
Differential Invariant Verification
    ↓
Adversarial Critic
    ↓
Security Regression Gate
    ↓
Adaptive Mutation Campaign
    ↓
Surviving Mutant → Targeted Test Generation → Retry
    ↓
Evidence-Backed Ship Gate
    ↓
Human Approval
    ↓
Git Commit
```

### Phase 1 Evaluation

Run the updated benchmark with:

```bash
cd backend
python eval_suite.py
```

The evaluation report now includes proof rate, invariant discovery/preservation, counterexamples, mutation score, security non-regression, and attempts per case.
