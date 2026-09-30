import os
import json
import docker
import base64
import logging

logger = logging.getLogger(__name__)

SANDBOX_IMAGE = "codeflow-sandbox:latest"

ANALYZER_SCRIPT = '''
import ast, json
src = open("/app/main.py").read()
tree = ast.parse(src)
try:
    from radon.complexity import cc_visit
    blocks = cc_visit(tree)
    avg_cc = round(sum(b.complexity for b in blocks) / max(len(blocks), 1), 2)
except Exception:
    avg_cc = None
try:
    from pyflakes import checker
    lint = len(checker.Checker(ast.parse(src), "main.py").messages)
except Exception:
    lint = None
funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
docs = sum(1 for f in funcs if ast.get_docstring(f))
print("JSON_START" + json.dumps({
    "avg_complexity": avg_cc,
    "lint_issues": lint,
    "functions": len(funcs),
    "docstring_coverage": round(docs / max(len(funcs), 1) * 100, 1),
    "lines": len(src.splitlines()),
}) + "JSON_END")
'''


class SandboxExecutor:
    def __init__(self):
        try:
            self.client = docker.from_env()
            self.client.ping()
            logger.info("Docker connection established.")
        except Exception as e:
            logger.error(f"Docker not available: {e}")
            self.client = None

    def ensure_image(self):
        try:
            self.client.images.get(SANDBOX_IMAGE)
        except docker.errors.ImageNotFound:
            logger.info("Sandbox image not found. Building (~60s)...")
            backend_dir = os.path.dirname(os.path.abspath(__file__))
            self.client.images.build(
                path=backend_dir,
                dockerfile="Dockerfile.sandbox",
                tag=SANDBOX_IMAGE,
                rm=True,
            )
            logger.info("Sandbox image built.")

    def _run(self, command: str, timeout: int = 20) -> dict:
        container = None
        try:
            container = self.client.containers.run(
                image=SANDBOX_IMAGE,
                command=["sh", "-c", command],
                detach=True,
                network_disabled=True,
                mem_limit="256m",
                auto_remove=False,
            )
            result = container.wait(timeout=timeout)
            logs = container.logs().decode("utf-8", errors="replace")
            return {"success": result.get("StatusCode", -1) == 0, "output": logs.strip()}
        except Exception as e:
            return {"success": False, "output": f"Execution error: {e}"}
        finally:
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    def _write_and_run(self, code: str, extra_cmd: str, timeout: int = 20) -> dict:
        ec = base64.b64encode(code.encode()).decode()
        command = f"echo '{ec}' | base64 -d > /app/main.py && {extra_cmd}"
        return self._run(command, timeout)

    def execute(self, code: str, test_code: str, timeout: int = 20) -> dict:
        if not self.client:
            return {"success": False, "output": "Docker is not running."}
        try:
            self.ensure_image()
        except Exception as e:
            return {"success": False, "output": f"Image build failed: {e}"}
        et = base64.b64encode(test_code.encode()).decode()
        extra = (
            f"echo '{et}' | base64 -d > /app/test_main.py && "
            f"cd /app && python -m pytest test_main.py -v --tb=short 2>&1"
        )
        result = self._write_and_run(code, extra, timeout)
        logger.info(f"--- SANDBOX RESULT (ok={result['success']}) ---\n{result['output']}\n--- END ---")
        return result

    def analyze(self, code: str) -> dict:
        if not self.client:
            return {}
        try:
            self.ensure_image()
        except Exception:
            return {}
        ea = base64.b64encode(ANALYZER_SCRIPT.encode()).decode()
        extra = f"echo '{ea}' | base64 -d > /app/_analyze.py && cd /app && python _analyze.py 2>/dev/null"
        result = self._write_and_run(code, extra, timeout=15)
        out = result["output"]
        start, end = out.find("JSON_START"), out.find("JSON_END")
        if start == -1 or end == -1:
            return {}
        try:
            return json.loads(out[start + len("JSON_START"):end])
        except Exception:
            return {}

    def security_scan(self, code: str) -> dict:
        """Runs bandit vulnerability scan inside the sandbox."""
        if not self.client:
            return {}
        try:
            self.ensure_image()
        except Exception:
            return {}
        extra = "cd /app && python -m bandit -q -f json main.py 2>/dev/null || true"
        result = self._write_and_run(code, extra, timeout=20)
        out = result["output"]
        s, e = out.find("{"), out.rfind("}")
        if s == -1 or e == -1:
            return {"issues": 0, "high": 0, "medium": 0, "low": 0}
        try:
            data = json.loads(out[s:e + 1])
            issues = data.get("results", [])
            return {
                "issues": len(issues),
                "high": sum(1 for i in issues if i.get("issue_severity") == "HIGH"),
                "medium": sum(1 for i in issues if i.get("issue_severity") == "MEDIUM"),
                "low": sum(1 for i in issues if i.get("issue_severity") == "LOW"),
            }
        except Exception:
            return {"issues": 0, "high": 0, "medium": 0, "low": 0}