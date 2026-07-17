"""One-call implicit acquisition.

`acquire_context` is the implicit front door: give it a target and any number of
loose context paths (or none) and it sniffs each input, runs the right adapter,
folds everything into a single target-bound acquisition bundle, and registers
that bundle so every downstream consumer can rediscover it from the target
alone.  No context flags, no bundle paths, no env vars required.

All acquired data is advisory evidence; compile and objdiff gates remain the
acceptance boundary.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from . import acquisition_registry as registry
from .context_pack import build_context_pack
from .discovery import route_inputs, sniff_path
from .ghidra_context import export_ghidra_context
from .targets import identify_binary


def _target_json(input_path: Path | None, preferred_name: str | None) -> dict[str, Any]:
    if input_path is None:
        return {}
    try:
        identity = identify_binary(input_path, preferred_name)
    except (FileNotFoundError, OSError, ValueError):
        return {}
    return identity.to_json()


def _has_target_identity(target: dict[str, Any]) -> bool:
    return bool(target.get("sha256") or target.get("stableId"))


def acquire_context(
    *,
    target_input: Path | None,
    context_paths: list[Path] | None = None,
    out_dir: Path,
    preferred_name: str | None = None,
    repo_root: Path | None = None,
    ghidra: Path | None = None,
    project_snapshot: Path | None = None,
    register: bool = True,
    max_files: int = 500,
) -> dict[str, Any]:
    """Sniff, extract, bundle, and register in one call.

    `target_input` supplies target identity for fingerprinting and can itself be
    sniffed as a binary source for Ghidra extraction.  `context_paths` are extra
    loose artifacts; each is auto-routed.
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    repo_root = repo_root or Path.cwd()
    inputs: list[Path] = list(context_paths or [])
    if target_input is not None:
        try:
            sniffed = sniff_path(target_input)
        except (OSError, ValueError):
            sniffed = None
        if sniffed is not None and sniffed.adapter == "ghidra" and target_input not in inputs:
            inputs.insert(0, target_input)
    routed = route_inputs(inputs)

    target = _target_json(target_input, preferred_name)

    ghidra_reports: list[dict[str, Any]] = []
    derived_context: list[Path] = list(routed.context_paths)
    ghidra_errors: list[dict[str, Any]] = []
    for source in routed.ghidra_sources:
        ghidra_out = out_dir / "ghidra" / source.path.stem
        try:
            report = export_ghidra_context(
                source=source.path,
                out_dir=ghidra_out,
                ghidra=ghidra,
                project_snapshot=project_snapshot,
            )
            ghidra_reports.append(report)
            facts_jsonl = Path(str(report.get("factsJsonl") or ""))
            if facts_jsonl.exists():
                derived_context.append(facts_jsonl)
        except (RuntimeError, ValueError, FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
            ghidra_errors.append({"source": str(source.path), "error": str(exc)})

    pack_manifest = build_context_pack(
        contexts=derived_context,
        out_dir=out_dir / "context-pack",
        target=target,
        repo_root=repo_root,
        max_files=max_files,
    )

    bundle_dir = repo_root / str(pack_manifest["bundleDir"]) if not Path(str(pack_manifest["bundleDir"])).is_absolute() else Path(str(pack_manifest["bundleDir"]))
    bundle_manifest_path = bundle_dir / "manifest.json"
    bundle_manifest = json.loads(bundle_manifest_path.read_text(encoding="utf-8")) if bundle_manifest_path.exists() else {}

    registry_entry: dict[str, Any] | None = None
    can_register = register and bool(bundle_manifest) and _has_target_identity(target)
    if can_register:
        try:
            registry_entry = registry.register_bundle(
                bundle_dir=bundle_dir,
                manifest=bundle_manifest,
                repo_root=repo_root,
                label=preferred_name or (Path(str(target.get("binaryPath"))).name if target.get("binaryPath") else None),
            )
        except ValueError:
            registry_entry = None
            can_register = False

    if target_input is not None and not _has_target_identity(target):
        status = "failed"
    elif register and not can_register and not registry_entry:
        status = "partial" if bundle_manifest else "failed"
    else:
        status = "complete"

    return {
        "schema": "agentdecompile.acquire.v1",
        "status": status,
        "target": target,
        "targetFingerprint": bundle_manifest.get("targetFingerprint") if _has_target_identity(target) else None,
        "routing": routed.to_json(),
        "ghidraReports": ghidra_reports,
        "ghidraErrors": ghidra_errors,
        "contextPack": pack_manifest,
        "bundleDir": str(bundle_dir),
        "registered": registry_entry is not None,
        "registryEntry": registry_entry,
        "claimBoundary": "acquired context is advisory evidence only; compile and objdiff gates remain required.",
    }
