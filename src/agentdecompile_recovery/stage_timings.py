"""Accumulate wall-time stage receipts for one-shot / reconstruct runs."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .state import atomic_write_json, now

SCHEMA = "agentdecompile.stage-timings.v1"


def empty_timings(work_dir: Path) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "writtenAt": now(),
        "workDir": str(work_dir),
        "stages": {},
        "claimBoundary": "Wall times only; not a recovery-quality claim.",
    }


def record_stage(
    timings: dict[str, Any],
    name: str,
    *,
    started: float,
    ended: float | None = None,
    **extra: Any,
) -> None:
    end = time.monotonic() if ended is None else ended
    stages = timings.setdefault("stages", {})
    stages[name] = {
        "wallSeconds": round(end - started, 3),
        **extra,
    }
    timings["writtenAt"] = now()


def write_stage_timings(work_dir: Path, timings: dict[str, Any]) -> Path:
    path = work_dir / "stage-timings.json"
    timings = {**timings, "workDir": str(work_dir), "writtenAt": now()}
    atomic_write_json(path, timings)
    return path
