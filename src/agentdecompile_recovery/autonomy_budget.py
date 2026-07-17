"""Bounded autonomy budgets for reconstruct --autonomous loops.

Keeps vacuum/repair from becoming unbounded API or wall-clock spend. Budgets are
receipts, not claims: exhausting a budget is a typed stop, not a match.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .state import atomic_write_json, now

SCHEMA = "agentdecompile.autonomy-budget.v1"
DEFAULT_MAX_FUNCTIONS = 1
DEFAULT_MAX_ATTEMPTS_PER_FUNCTION = 3
CLAIM_BOUNDARY = (
    "autonomy budget bounds repair/vacuum loops only; it does not establish "
    "objdiff-verified-semantic recovery"
)


@dataclass(frozen=True)
class AutonomyBudget:
    """Hard caps for advanced --autonomous vacuum/repair."""

    max_functions: int = DEFAULT_MAX_FUNCTIONS
    max_attempts_per_function: int = DEFAULT_MAX_ATTEMPTS_PER_FUNCTION
    max_wall_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.max_functions < 0:
            raise ValueError("max_functions must be >= 0")
        if self.max_attempts_per_function < 1:
            raise ValueError("max_attempts_per_function must be >= 1")
        if self.max_wall_seconds is not None and self.max_wall_seconds < 1:
            raise ValueError("max_wall_seconds must be >= 1 when set")

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.update(
            {
                "schema": SCHEMA,
                "claimBoundary": CLAIM_BOUNDARY,
            }
        )
        return payload

    def vacuum_bridge_args(self, *, queue: Path) -> list[str] | None:
        """Args for decomp-cli vacuum start, or None when the function budget is zero."""

        if self.max_functions <= 0:
            return None
        args = [
            "vacuum",
            "start",
            "--queue",
            str(queue),
            "--max-functions",
            str(self.max_functions),
            "--max-attempts",
            str(self.max_attempts_per_function),
        ]
        if self.max_wall_seconds is not None:
            # vacuum.sh accepts --timeout with a duration suffix (e.g. 120s).
            args.extend(["--timeout", f"{int(self.max_wall_seconds)}s"])
        return args


def ensure_vacuum_queue(queue: Path) -> Path:
    """Create an empty vacuum queue under the reconstruct work dir if missing."""

    queue.parent.mkdir(parents=True, exist_ok=True)
    if not queue.exists():
        atomic_write_json(
            queue,
            {
                "schema": "agentdecompile.vacuum-queue.v1",
                "pending": [],
                "matched": [],
                "integrated": [],
                "failed": [],
                "difficult": [],
                "attempts": {},
            },
        )
    return queue


def budget_from_args(
    *,
    max_functions: int | None = None,
    max_attempts_per_function: int | None = None,
    max_wall_seconds: int | None = None,
) -> AutonomyBudget:
    return AutonomyBudget(
        max_functions=DEFAULT_MAX_FUNCTIONS if max_functions is None else max_functions,
        max_attempts_per_function=(
            DEFAULT_MAX_ATTEMPTS_PER_FUNCTION
            if max_attempts_per_function is None
            else max_attempts_per_function
        ),
        max_wall_seconds=max_wall_seconds,
    )


def write_autonomy_budget_receipt(
    work_dir: Path,
    budget: AutonomyBudget,
    *,
    requested: bool,
    status: str,
    reason: str | None = None,
    bridge_args: list[str] | None = None,
    bridge_returncode: int | None = None,
) -> Path:
    """Persist autonomy budget + outcome under the run directory."""

    path = work_dir / "autonomy-budget.json"
    payload: dict[str, Any] = {
        **budget.to_json(),
        "requested": bool(requested),
        "status": status,
        "writtenAt": now(),
    }
    if reason:
        payload["reason"] = reason
    if bridge_args is not None:
        payload["bridgeArgs"] = list(bridge_args)
    if bridge_returncode is not None:
        payload["bridgeReturncode"] = int(bridge_returncode)
    atomic_write_json(path, payload)
    return path


def remaining_attempts(*, attempts_seen: int, budget: AutonomyBudget) -> int:
    return max(0, budget.max_attempts_per_function - max(0, attempts_seen))
