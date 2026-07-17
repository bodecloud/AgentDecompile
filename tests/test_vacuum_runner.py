"""Unit tests for reconstruct vacuum runner → plugin pipeline bridge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentdecompile_recovery.autonomy_budget import AutonomyBudget, reconstruct_vacuum_runner_command
from agentdecompile_recovery.vacuum_runner import already_verified, find_source_task, run_vacuum_prompt

pytestmark = pytest.mark.unit


def _task(name: str, *, complete_slice: bool = True) -> dict[str, Any]:
    task: dict[str, Any] = {
        "name": name,
        "entry": "0x401000",
        "status": "generated-unverified",
        "source": "candidate.c",
        "semanticSource": True,
    }
    if complete_slice:
        task["targetSlice"] = {
            "status": "complete",
            "bytesPath": "slice.bin",
            "bodyBytes": 4,
        }
    return task


def test_find_source_task_and_already_verified(tmp_path: Path) -> None:
    work = tmp_path / "run"
    gen = work / "source-generation"
    gen.mkdir(parents=True)
    (gen / "tasks.jsonl").write_text(json.dumps(_task("FUN_401000")) + "\n", encoding="utf-8")
    assert find_source_task(work, "FUN_401000")["name"] == "FUN_401000"
    assert find_source_task(work, "missing") is None
    (work / "verified").mkdir()
    (work / "verified" / "FUN_401000_401000.c").write_text("int x(void){return 0;}\n", encoding="utf-8")
    assert already_verified(work, "FUN_401000") is True


def test_run_vacuum_prompt_missing_and_unsuitable(tmp_path: Path) -> None:
    work = tmp_path / "run"
    work.mkdir()
    missing = run_vacuum_prompt(work_dir=work, name="gone")
    assert missing["exitCode"] == 2
    assert missing["status"] == "missing-task"

    gen = work / "source-generation"
    gen.mkdir()
    (gen / "tasks.jsonl").write_text(json.dumps(_task("alpha", complete_slice=False)) + "\n", encoding="utf-8")
    bad = run_vacuum_prompt(work_dir=work, name="alpha")
    assert bad["exitCode"] == 2
    assert bad["status"] == "unsuitable-task"


def test_run_vacuum_prompt_uses_plugin_pipeline(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    work = tmp_path / "run"
    gen = work / "source-generation"
    gen.mkdir(parents=True)
    slice_path = gen / "slice.bin"
    slice_path.write_bytes(b"\x90\x90\xc3\x00")
    src = gen / "candidate.c"
    src.write_text("int alpha(void){return 0;}\n", encoding="utf-8")
    task = _task("alpha")
    task["source"] = str(src)
    task["targetSlice"]["bytesPath"] = str(slice_path)
    (gen / "tasks.jsonl").write_text(json.dumps(task) + "\n", encoding="utf-8")

    calls: list[Any] = []

    def fake_pipeline(config: Any) -> dict[str, Any]:
        calls.append(config)
        out = Path(config.out_dir)
        matches = out / "plugin-code-slice-matches.jsonl"
        matches.parent.mkdir(parents=True, exist_ok=True)
        matches.write_text(
            json.dumps(
                {
                    "name": "alpha",
                    "entry": "0x401000",
                    "differences": 0,
                    "status": "matched",
                    "source": str(src),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return {
            "status": "complete",
            "successfulFunctions": 1,
            "failedFunctions": 0,
            "inspectedFunctions": 1,
            "codeSliceMatchesPath": str(matches),
        }

    monkeypatch.setattr(
        "agentdecompile_recovery.vacuum_runner.run_source_plugin_pipeline",
        fake_pipeline,
    )
    result = run_vacuum_prompt(work_dir=work, name="alpha", max_attempts=2)
    assert result["exitCode"] == 0
    assert result["status"] == "matched"
    assert calls and calls[0].max_retries == 2
    assert any(path.name.endswith(".c") for path in (work / "verified").iterdir())


def test_reconstruct_vacuum_runner_command_includes_placeholders(tmp_path: Path) -> None:
    cmd = reconstruct_vacuum_runner_command(tmp_path, max_attempts=4)
    assert "agentdecompile_recovery.vacuum_runner" in cmd
    assert "{{name}}" in cmd
    assert "{{promptDir}}" in cmd
    assert "--max-attempts 4" in cmd
    budget = AutonomyBudget(max_functions=1, max_attempts_per_function=4)
    args = budget.vacuum_bridge_args(
        queue=tmp_path / "state" / "queue.json",
        prompts_dir=tmp_path / "prompts",
        work_dir=tmp_path,
        runner_command=cmd,
    )
    assert args is not None
    assert "--runner-command" in args
    assert "--no-sleep" in args
    assert str(tmp_path / "state" / "scores.json") in args
