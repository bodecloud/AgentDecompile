"""Regression test: packaged-source candidates that call other sub_XXXX/
FUN_XXXX functions must declare the callee's real calling convention,
not silently let it default to cdecl.

Found during the swkotor.exe cache sweep: sub_88c0's real target calls
sub_7830 (2 args) with no stack cleanup after the call (`call sub_7830 / ret
0x4`), because sub_7830 is itself __stdcall and cleans its own 8 bytes. The
packaged-source candidate for sub_88c0 has no prototype for sub_7830 in
scope, so the implicit C declaration defaults to cdecl and the caller wrongly
emits `add esp, 0x8` after the call -- a real instruction-stream mismatch,
not just a symbol-naming issue.

infer_callee_prototype()/infer_callee_prototypes() fix this by reusing the
callee's own packaged-source candidate.c (a sibling directory under the same
source-generation root) and running it back through the same
infer_packaged_callconv()/packaged_stack_bytes() inference already used for
the caller itself, to emit a correctly-decorated extern prototype before the
caller's body.
"""

from __future__ import annotations

from pathlib import Path

from agentdecompile_recovery.source_parity_synthesize import (
    infer_callee_prototype,
    infer_callee_prototypes,
)


def _write_callee_candidate(root: Path, name: str, entry: str, source: str) -> None:
    directory = root / f"{name}_{entry}"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "candidate.c").write_text(source, encoding="utf-8")


def test_infer_callee_prototype_declares_stdcall_from_sibling_candidate(tmp_path: Path) -> None:
    _write_callee_candidate(
        tmp_path,
        "sub_7830",
        "407830",
        "undefined4 __stdcall sub_7830(undefined4 param_1,int param_2)\n\n{\n  return 1;\n}\n",
    )

    prototype = infer_callee_prototype("sub_7830", tmp_path)

    assert prototype == "extern void __stdcall sub_7830(unsigned int, unsigned int);"


def test_infer_callee_prototype_returns_none_for_cdecl_callee(tmp_path: Path) -> None:
    _write_callee_candidate(
        tmp_path,
        "sub_1e5670",
        "41e5670",
        "void sub_1e5670(int param_1)\n\n{\n  return;\n}\n",
    )

    assert infer_callee_prototype("sub_1e5670", tmp_path) is None


def test_infer_callee_prototype_returns_none_when_sibling_missing(tmp_path: Path) -> None:
    assert infer_callee_prototype("sub_deadbeef", tmp_path) is None


def test_infer_callee_prototypes_skips_self_recursive_calls(tmp_path: Path) -> None:
    _write_callee_candidate(
        tmp_path,
        "sub_1060",
        "401060",
        "undefined4 __stdcall sub_1060(undefined4 param_1)\n\n{\n  return sub_1060(param_1);\n}\n",
    )
    source = "undefined4 __stdcall sub_1060(undefined4 param_1)\n\n{\n  return sub_1060(param_1);\n}\n"

    assert infer_callee_prototypes(source, "sub_1060", tmp_path) == ""


def test_infer_callee_prototypes_declares_multiple_callees(tmp_path: Path) -> None:
    _write_callee_candidate(
        tmp_path,
        "sub_7830",
        "407830",
        "undefined4 __stdcall sub_7830(undefined4 param_1,int param_2)\n\n{\n  return 1;\n}\n",
    )
    _write_callee_candidate(
        tmp_path,
        "sub_7fe0",
        "407fe0",
        "undefined4 __stdcall sub_7fe0(undefined4 param_1,int param_2)\n\n{\n  return 1;\n}\n",
    )
    source = (
        "void __stdcall sub_88e0(undefined4 param_1)\n\n"
        "{\n  sub_7830(param_1, 2);\n  sub_7fe0(param_1, 2);\n}\n"
    )

    prototypes = infer_callee_prototypes(source, "sub_88e0", tmp_path)

    assert "extern void __stdcall sub_7830(unsigned int, unsigned int);" in prototypes
    assert "extern void __stdcall sub_7fe0(unsigned int, unsigned int);" in prototypes
