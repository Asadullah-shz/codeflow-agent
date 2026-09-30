"""Episodic Reflexion Memory — the agent learns from past failures (SQLite)."""

import os
import re
import time
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_memory.db")


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.execute(
        """CREATE TABLE IF NOT EXISTS experiences(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signature TEXT,
            error_snippet TEXT,
            lesson TEXT,
            created_at REAL)"""
    )
    return c


def signature_of(error_text: str) -> str:
    m = re.search(r"\b(\w*(?:Error|Exception))\b", error_text)
    if m:
        return m.group(1)
    first = next((l.strip() for l in error_text.splitlines() if l.strip()), "unknown")
    return first[:60]


def recall(sig: str):
    c = _conn()
    row = c.execute(
        "SELECT lesson FROM experiences WHERE signature=? ORDER BY created_at DESC LIMIT 1",
        (sig,),
    ).fetchone()
    c.close()
    return row[0] if row else None


def remember(sig: str, error_snippet: str, lesson: str):
    c = _conn()
    c.execute(
        "INSERT INTO experiences(signature, error_snippet, lesson, created_at) VALUES(?,?,?,?)",
        (sig, error_snippet[:300], lesson, time.time()),
    )
    c.commit()
    c.close()