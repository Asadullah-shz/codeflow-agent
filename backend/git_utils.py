import os
import subprocess
import time
import logging

logger = logging.getLogger(__name__)
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

def commit_code(code: str, test_code: str, commit_msg: str) -> str:
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # Initialize git repo if it doesn't exist
    if not os.path.exists(os.path.join(OUTPUT_DIR, ".git")):
        try:
            subprocess.run(["git", "init", "-b", "main"], cwd=OUTPUT_DIR, capture_output=True)
            subprocess.run(["git", "config", "user.email", "agent@codeflow.ai"], cwd=OUTPUT_DIR, capture_output=True)
            subprocess.run(["git", "config", "user.name", "CodeFlow Agent"], cwd=OUTPUT_DIR, capture_output=True)
        except FileNotFoundError:
            logger.warning("Git not found in PATH. Falling back to local file save only.")

    timestamp = int(time.time())
    main_path = os.path.join(OUTPUT_DIR, f"refactored_{timestamp}.py")
    test_path = os.path.join(OUTPUT_DIR, f"test_refactored_{timestamp}.py")

    with open(main_path, "w", encoding="utf-8") as f:
        f.write(code)
    with open(test_path, "w", encoding="utf-8") as f:
        f.write(test_code)

    try:
        subprocess.run(["git", "add", "."], cwd=OUTPUT_DIR, capture_output=True)
        res = subprocess.run(["git", "commit", "-m", commit_msg], cwd=OUTPUT_DIR, capture_output=True, text=True)
        if res.returncode == 0:
            hash_res = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=OUTPUT_DIR, capture_output=True, text=True)
            return f"✅ Committed to local Git repo as {hash_res.stdout.strip()}"
        return "✅ Files saved to output/ (Nothing new to commit to Git)"
    except FileNotFoundError:
        return f"✅ Files saved to output/ (Git not available for commit)"