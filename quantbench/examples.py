from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from quantbench.config import RUNS_DIR

# Pre-generated example sessions shipped with the package. These are real research runs (natural
# language request -> universe -> backtest -> Reviewer + Critic -> artifacts), captured once and
# frozen here. On first open, seed_example_runs restores them into the user's runs dir so the
# sidebar shows a ready "example project" of genuine conversations to explore and continue.
BUNDLE_DIR = Path(__file__).resolve().parent / "data" / "seeds" / "examples"


def example_index() -> list[dict[str, Any]]:
    index_path = BUNDLE_DIR / "index.json"
    if not index_path.exists():
        return []
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    examples = payload.get("examples", [])
    return examples if isinstance(examples, list) else []


def seed_example_runs(runs_dir: Path = RUNS_DIR) -> dict[str, Any]:
    """Restore the bundled example sessions into runs_dir, skipping any already present.

    Idempotent: re-running only copies examples the user does not already have, so it is safe to
    call on every startup.
    """

    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir = runs_dir / "_sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    created_runs: list[str] = []
    created_sessions: list[str] = []
    for example in example_index():
        run_id = example.get("run_id")
        session_id = example.get("session_id")

        if run_id:
            src_run = BUNDLE_DIR / "runs" / run_id
            dst_run = runs_dir / run_id
            if src_run.is_dir() and not dst_run.exists():
                shutil.copytree(src_run, dst_run)
                created_runs.append(run_id)

        if session_id:
            src_session = BUNDLE_DIR / "_sessions" / f"{session_id}.json"
            dst_session = sessions_dir / f"{session_id}.json"
            if src_session.exists() and not dst_session.exists():
                shutil.copy2(src_session, dst_session)
                created_sessions.append(session_id)

    return {
        "created": len(created_runs),
        "run_ids": created_runs,
        "session_ids": created_sessions,
    }
