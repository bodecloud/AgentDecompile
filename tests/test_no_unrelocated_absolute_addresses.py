"""U4 of docs/plans/2026-07-30-001-fix-generalize-relocation-evidence-plan.md.

**Scope correction (documented in the plan's amended Key Technical
Decisions):** the plan originally set out to guard against rule generators
that embed a raw absolute address in generated C source *without* populating
`absoluteAddressRelocations`. Real-toolchain investigation (real MSVC8/wine
compile + real objdiff) overturned that premise: `absoluteAddressRelocations`
only helps when the candidate's own compiled object references the address
through a compiler-emitted relocation (a named `extern` symbol) -- not a raw
literal pointer cast (`*(unsigned int *)0x...`), which MSVC compiles as a bare
immediate with no relocation. Adding the evidence to a literal-cast candidate
was A/B tested and found to make matching *worse* (spurious
`ARGUMENT_MISMATCH` entries), not better -- confirmed for
`global_and_global_bool` and for one of the ten single-address rules this
plan's U2 originally (and incorrectly) wired up, then reverted.

This test guards the corrected, real anti-pattern instead: a rule generator
must never populate `absoluteAddressRelocations` for an address its own
generated source only references via a literal pointer cast. `inc_abs_global`
is exempt from this check -- its own literal-cast candidates are unaffected
either way (real-toolchain A/B testing showed identical results with and
without the evidence), and the evidence field exists there specifically so a
*different*, later-constructed candidate for the same target (e.g. a
subagent rewrite referencing a named `DAT_<addr>` symbol, per
docs/solutions/architecture-patterns/rewrite-queue-subagent-fulfillment.md)
can carry matching relocation evidence of its own. Extending that
inheritance to fire automatically for every packaged-source/rewrite
candidate is a distinct, deferred piece of work -- see the plan's Scope
Boundaries.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

SOURCE_PATH = Path(__file__).resolve().parent.parent / "src" / "agentdecompile_recovery" / "source_parity_synthesize.py"

# Rules exempt from this check: their own literal-cast candidate is
# unaffected by the evidence (verified real-toolchain neutral, not harmful),
# and the evidence exists to serve a different, later-constructed candidate.
EXEMPT_RULE_FUNCTIONS = {"inc_abs_global"}

LITERAL_CAST_RE = re.compile(r"\*\s*\([^)]*\*\)\s*0x\{[a-zA-Z_]+")


def _iter_rule_generator_functions(tree: ast.Module) -> list[ast.FunctionDef]:
    functions = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        args = [a.arg for a in node.args.args]
        if args[:3] == ["row", "c_name", "data"]:
            functions.append(node)
    return functions


def _function_source(source_lines: list[str], node: ast.FunctionDef) -> str:
    return "\n".join(source_lines[node.lineno - 1 : node.end_lineno])


def test_no_rule_generator_pairs_relocation_evidence_with_a_literal_cast() -> None:
    text = SOURCE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(text)
    source_lines = text.splitlines()

    violations = []
    for node in _iter_rule_generator_functions(tree):
        if node.name in EXEMPT_RULE_FUNCTIONS:
            continue
        body = _function_source(source_lines, node)
        if "absoluteAddressRelocations" not in body:
            continue
        if LITERAL_CAST_RE.search(body):
            violations.append(node.name)

    assert violations == [], (
        f"Rule generator(s) {violations} populate absoluteAddressRelocations "
        "while their generated source only references the address via a "
        "literal pointer cast -- real-toolchain testing showed this makes "
        "objdiff matching worse, not better (see this test's module "
        "docstring). Either remove the evidence, or change the generated "
        "source to reference the address through a named extern symbol."
    )


def test_check_actually_detects_the_anti_pattern() -> None:
    """Regression guard on the check itself: prove it fires on a synthetic
    function shaped exactly like the mistake this test exists to prevent.
    """

    synthetic_source = (
        "def fake_rule(row: dict[str, Any], c_name: str, data: bytes) -> list[GeneratedCandidate]:\n"
        "    addr = u32(data[2:6])\n"
        '    source = f"*(unsigned int *)0x{addr:08x} = 1;"\n'
        "    return [GeneratedCandidate(\n"
        '        rule="fake", variant="fake", c_name=c_name, symbol=c_name,\n'
        "        source=source, callconv=\"cdecl\", return_type=\"void\",\n"
        '        evidence={"absoluteAddressRelocations": [{"offset": 2}]},\n'
        "    )]\n"
    )
    tree = ast.parse(synthetic_source)
    source_lines = synthetic_source.splitlines()
    functions = _iter_rule_generator_functions(tree)
    assert len(functions) == 1
    body = _function_source(source_lines, functions[0])
    assert "absoluteAddressRelocations" in body
    assert LITERAL_CAST_RE.search(body) is not None
