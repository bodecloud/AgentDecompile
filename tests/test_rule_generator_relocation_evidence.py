"""Regression tests: 10 mechanical rule generators now populate
absoluteAddressRelocations, closing the same target-side rendering gap
inc_abs_global had (PR #149) -- see
docs/plans/2026-07-30-001-fix-generalize-relocation-evidence-plan.md, U2.

Each test constructs a byte pattern that satisfies the rule's own guard
clause, calls the generator, and asserts every returned GeneratedCandidate
carries the correct absoluteAddressRelocations entry (or entries, for rules
returning multiple variants built from the same address) -- plus an
integration check that render_target_coff_for_candidate() actually emits a
`.long <symbol>` relocation instead of a raw byte blob for the address slice.
"""

from __future__ import annotations

from agentdecompile_recovery.source_parity_synthesize import (
    call_indirect_zero,
    float_multiply_global,
    global_field_eq_one_bool,
    global_indexed_store_cdecl,
    global_setter_u32_stdcall,
    global_virtual_call_stack_arg,
    import_call_arg_return_one_stdcall8,
    import_call_return_self,
    import_call_self_stdcall,
    render_target_coff_for_candidate,
    virtual_call_eq_global,
)


def _assert_relocation(evidence: dict, *, offset: int, addr: int) -> None:
    relocations = evidence.get("absoluteAddressRelocations")
    assert isinstance(relocations, list) and len(relocations) == 1
    relocation = relocations[0]
    assert relocation["offset"] == offset
    assert relocation["type"] == "IMAGE_REL_I386_DIR32"
    assert relocation["symbol"] == f"_DAT_{addr:08x}"
    assert relocation["decodedAddress"] == f"0x{addr:08x}"


def test_float_multiply_global_relocation_evidence() -> None:
    addr = 0x00830540
    data = b"\xd9\x44\x24\x04\xd8\x0d" + addr.to_bytes(4, "little") + b"\xc3"
    candidates = float_multiply_global({}, "FUN_test", data)
    assert len(candidates) == 1
    _assert_relocation(candidates[0].evidence, offset=6, addr=addr)

    rendered = render_target_coff_for_candidate(candidates[0], data)
    assert f".long _DAT_{addr:08x}" in rendered["asm"]


def test_import_call_self_stdcall_relocation_evidence() -> None:
    addr = 0x00404000
    data = b"\x51\xff\x15" + addr.to_bytes(4, "little") + b"\xc3"
    candidates = import_call_self_stdcall({}, "FUN_test", data)
    assert len(candidates) == 1
    _assert_relocation(candidates[0].evidence, offset=3, addr=addr)

    rendered = render_target_coff_for_candidate(candidates[0], data)
    assert f".long _DAT_{addr:08x}" in rendered["asm"]


def test_global_setter_u32_stdcall_relocation_evidence() -> None:
    addr = 0x00830544
    data = b"\x8b\x44\x24\x04\xa3" + addr.to_bytes(4, "little") + b"\xc2\x04\x00"
    candidates = global_setter_u32_stdcall({}, "FUN_test", data)
    assert len(candidates) == 1
    _assert_relocation(candidates[0].evidence, offset=5, addr=addr)

    rendered = render_target_coff_for_candidate(candidates[0], data)
    assert f".long _DAT_{addr:08x}" in rendered["asm"]


def test_call_indirect_zero_relocation_evidence_both_variants() -> None:
    addr = 0x00405000
    data = b"\x6a\x00\xff\x15" + addr.to_bytes(4, "little") + b"\xc3"
    candidates = call_indirect_zero({}, "FUN_test", data)
    assert len(candidates) == 2
    for candidate in candidates:
        _assert_relocation(candidate.evidence, offset=4, addr=addr)
        rendered = render_target_coff_for_candidate(candidate, data)
        assert f".long _DAT_{addr:08x}" in rendered["asm"]


def test_virtual_call_eq_global_relocation_evidence_both_variants() -> None:
    addr = 0x00830548
    data = b"\x8b\x01\xff\x50\x04\x3b\x05" + addr.to_bytes(4, "little") + b"\x0f\x94\xc0\xc3"
    candidates = virtual_call_eq_global({}, "FUN_test", data)
    assert len(candidates) == 2
    for candidate in candidates:
        _assert_relocation(candidate.evidence, offset=7, addr=addr)
        rendered = render_target_coff_for_candidate(candidate, data)
        assert f".long _DAT_{addr:08x}" in rendered["asm"]


def test_import_call_return_self_relocation_evidence() -> None:
    addr = 0x00406000
    data = b"\x56\x8b\xf1\x56\xff\x15" + addr.to_bytes(4, "little") + b"\x8b\xc6\x5e\xc3"
    candidates = import_call_return_self({}, "FUN_test", data)
    assert len(candidates) == 1
    _assert_relocation(candidates[0].evidence, offset=6, addr=addr)

    rendered = render_target_coff_for_candidate(candidates[0], data)
    assert f".long _DAT_{addr:08x}" in rendered["asm"]


def test_global_indexed_store_cdecl_relocation_evidence() -> None:
    addr = 0x0083054C
    data = b"\x8b\x44\x24\x08\x8b\x4c\x24\x04\x89\x04\x8d" + addr.to_bytes(4, "little") + b"\xc3"
    candidates = global_indexed_store_cdecl({}, "FUN_test", data)
    assert len(candidates) == 1
    _assert_relocation(candidates[0].evidence, offset=11, addr=addr)

    rendered = render_target_coff_for_candidate(candidates[0], data)
    assert f".long _DAT_{addr:08x}" in rendered["asm"]


def test_import_call_arg_return_one_stdcall8_relocation_evidence_both_variants() -> None:
    addr = 0x00407000
    data = b"\xff\x74\x24\x04\xff\x15" + addr.to_bytes(4, "little") + b"\x33\xc0\x40\xc2\x08\x00"
    candidates = import_call_arg_return_one_stdcall8({}, "FUN_test", data)
    assert len(candidates) == 2
    for candidate in candidates:
        _assert_relocation(candidate.evidence, offset=6, addr=addr)
        rendered = render_target_coff_for_candidate(candidate, data)
        assert f".long _DAT_{addr:08x}" in rendered["asm"]


def test_global_virtual_call_stack_arg_relocation_evidence_both_variants() -> None:
    addr = 0x00830550
    data = (
        b"\x8b\x0d"
        + addr.to_bytes(4, "little")
        + b"\x8b\x54\x24\x04\x8b\x01\x52\xff\x50\x04\xc3"
    )
    candidates = global_virtual_call_stack_arg({}, "FUN_test", data)
    assert len(candidates) == 2
    for candidate in candidates:
        _assert_relocation(candidate.evidence, offset=2, addr=addr)
        rendered = render_target_coff_for_candidate(candidate, data)
        assert f".long _DAT_{addr:08x}" in rendered["asm"]


def test_global_field_eq_one_bool_relocation_evidence() -> None:
    addr = 0x00830554
    data = (
        b"\xa1"
        + addr.to_bytes(4, "little")
        + b"\x8b\x48\x08\x8b\x11\x33\xc0\x83\xfa\x01\x0f\x94\xc0\xc3"
    )
    candidates = global_field_eq_one_bool({}, "FUN_test", data)
    assert len(candidates) == 1
    _assert_relocation(candidates[0].evidence, offset=1, addr=addr)

    rendered = render_target_coff_for_candidate(candidates[0], data)
    assert f".long _DAT_{addr:08x}" in rendered["asm"]
