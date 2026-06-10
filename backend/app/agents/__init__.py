"""Loader for built-in agent instructions.

The base instructions for the system's built-in AI workers (Reception, Orchestrator,
UI Designer, ...) and the standard feature-generation policy are stored as Markdown
files in this directory, version-controlled in the repo. They are loaded at runtime
and injected into the agents' prompts — so prompts are config, not hard-coded.

Edit the .md files to change agent behaviour; no code change needed.
"""
from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).parent

# Roster of workers that exist from the start (the build-time pipeline). Each
# references the policy + its own instruction file when acting.
BUILTIN_WORKERS = [
    {"id": "reception", "instruction_file": "reception.md"},
    {"id": "orchestrator", "instruction_file": "orchestrator.md"},
    {"id": "ui_designer", "instruction_file": "ui_designer.md"},
    {"id": "reviewer", "instruction_file": "reviewer.md"},
    {"id": "tester", "instruction_file": "tester.md"},
    {"id": "feature_worker", "instruction_file": "feature_worker.md"},
]


@lru_cache
def load(name: str) -> str:
    """Load an instruction file by name (without .md). Empty string if missing."""
    path = _DIR / f"{name}.md"
    return path.read_text(encoding="utf-8").strip() if path.exists() else ""


def policy() -> str:
    """The standard feature-generation policy all build-time agents must follow."""
    return load("policy")
