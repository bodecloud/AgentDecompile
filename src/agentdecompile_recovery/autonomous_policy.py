"""Evidence-driven retry policy for source recovery plugin loops."""

from __future__ import annotations

from typing import Any


def choose_next_action(context: dict[str, Any], previous_attempts: list[dict[str, Any]]) -> dict[str, Any]:
    """Classify the next autonomous action from the latest attempt evidence."""

    latest = previous_attempts[-1] if previous_attempts else {}
    generator = latest.get("source-candidate-generator")
    verifier = latest.get("source-candidate-objdiff")
    row = context.get("sourceParityRow") if isinstance(context.get("sourceParityRow"), dict) else {}
    boundary_quality = ((row.get("targetSlice") or {}).get("boundaryQuality") or {}) if isinstance(row, dict) else {}
    best_diff = optional_int((verifier.data if verifier else {}).get("differenceCount"))
    verifier_error = (verifier.error if verifier else "") or ""
    generator_error = (generator.error if generator else "") or ""

    if generator and generator.status == "failure" and "no source candidate" in generator_error:
        action = "reacquire-or-expand-source-facts"
        reason = "candidate generator exhausted compatible source shapes"
    elif boundary_quality.get("status") == "suspect":
        action = "repair-boundary-before-retry"
        reason = "target slice boundary is suspect"
    elif "compile" in verifier_error.lower() or "syntax" in verifier_error.lower():
        action = "regenerate-source-shape"
        reason = "compiler rejected the selected source candidate"
    elif best_diff == 0:
        action = "promote-or-export"
        reason = "verifier reported zero differences"
    elif best_diff is not None and best_diff <= 8:
        action = "try-nearby-source-shape-or-permuter"
        reason = f"candidate is close to match with {best_diff} difference(s)"
    elif context.get("compilerProfiles") in (None, [], ()):
        action = "block-on-compiler-profile-evidence"
        reason = "large mismatch without compiler-profile evidence"
    else:
        action = "try-next-generated-candidate"
        reason = "previous candidate did not match"

    return {
        "schema": "agentdecompile.autonomous-policy-decision.v1",
        "action": action,
        "reason": reason,
        "attemptsSeen": len(previous_attempts),
        "bestDifferenceCount": best_diff,
        "boundaryQuality": boundary_quality.get("status"),
        "claimBoundary": "policy selects the next recovery action; it does not promote source without the verifier gate",
    }


def optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
