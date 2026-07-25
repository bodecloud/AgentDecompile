# Living plan: one-shot recovery performance

**Status:** active  
**Created:** 2026-07-24  
**Last updated:** 2026-07-24  
**Code:** `src/agentdecompile_recovery/`, `src/agentdecompile_cli/mcp_utils/batch_decompile.py`, `scripts/swkotor-match-*.py`  
**Implementation plan:** [2026-07-24-001-feat-idempotent-oneshot-perf-plan.md](2026-07-24-001-feat-idempotent-oneshot-perf-plan.md)

## Goal

One `agentdecompile-reconstruct` run should go from binary → single Ghidra analysis → inventory + batch decompile → match/synth → Borealis dump, using only this run's receipts. It should cover all inventoried functions (no skip-stage fastpath) and run much faster than today's ~20+ minute pre-synth wall. Verified still means objdiff zero — no shortcuts on the proof gate.

## Strategy links

See [STRATEGY.md](../../STRATEGY.md): matching recovery, export claim boundaries, and the one-shot performance track. We are not claiming 90% whole-binary parity, not promoting byte emitters, and not counting leftover artifacts as fresh output.

```mermaid
flowchart TD
  bin[Binary plus toolchain] --> ensure[ensure_analyzed_program]
  ensure --> inv[Export inventory -noanalysis]
  ensure --> dec[Batch decompile N threads]
  inv --> gates[Coverage gates]
  gates --> match[Match and synth]
  dec --> facts[Facts JSONL this run]
  match --> receipts[Receipts with sourceText]
  facts --> dump[Dump from declared inputs]
  receipts --> dump
  dump --> proof[MANIFEST and stage-timings]
```

## Baseline (2026-07-24, reference host)

| Stage | ~Wall | Notes |
|-------|------:|-------|
| Inventory autoanalysis | 185s | Decompiler Switch ~89–102s |
| ghidrecomp 2nd analysis | 205s | Same binary — redundant |
| Decompile 8621 fn | 342s @ 4 threads | `batch_decompile.py` defaults to 2 threads |
| Trivial+reloc match (cached) | 30–33s each | Shared WINEPREFIX under parallel load |
| Dump (pre-batching) | 426s | clang-format ×8k, slow disk |
| Dump (after batching) | tens–low hundreds s | Still dual advisory+Port; path-only rows without `sourceText` |
| Exhaustive MSVC synth | hours | Real coverage, not optional |

## Rules

1. **This run's artifacts.** Inventory, facts, match rows (`sourceText` at accept), and dump come from the current execution. `--resume`, cache, and `--dump-source-only` are operator tools ([AGENTS.md](../../AGENTS.md), [CRITICAL_PATH.md](../CRITICAL_PATH.md)).
2. **No coverage skip.** Shared analysis must not drop functions or bypass inventory gates for speed.
3. **Verified = objdiff zero.** Empty objdiff stdout and objdump fallback must not promote ([verifier honesty note](../doc-review-findings/2026-07-24-critical-path-verifier-honesty.md)).
4. **Declared dump inputs.** Fresh mode must not silently load undeclared sibling JSONL.

## Progress

**Done**

- Batched in-memory dump (`PendingWrites`), format-once-per-file, cached `clang-format` path
- Match writers embed `sourceText`; dump prefers embedded text + sha check
- Idempotency policy documented in AGENTS, `.cursorrules`, CRITICAL_PATH, STRATEGY
- **U1** Fail-closed proof gate: empty/unparseable objdiff, fallback rejected by `is_proven_zero`, emitter denylist, stale-object unlink, ladder denominator = function-candidates only
- **U2** Shared Ghidra analysis: `ensure_analyzed_program` + inventory `-process -noanalysis` (no `-deleteProject` on shared path)
- **U3** `thread_count` default `min(cpu,16)`; `batch-decompile` stage writes facts JSONL with `force_analysis=False`
- **U4** Fresh dump refuses undeclared siblings; match-cache keys include analysis-image digest; cache hits re-embed `sourceText`
- **U5** `--dump-layers` (default `verified,port`); `stage-timings.json` written per one-shot stage

**Delta update (2026-07-24)**

| Unit | Result |
|------|--------|
| U1–U5 | Landed on `feat/idempotent-oneshot-perf`; unit tests green for honesty, ghidra analysis, batch threads, fresh dump, layers, timings |
| Remaining scale | G14 per-worker Wine prefixes; G15 synth wall; G16 SSD work-dir guidance (operator) |

**Next**

1. Optional per-worker Wine prefixes (G14)
2. Synth wall-time / compile cache (G15) without skipping inventory

## Backlog

### P0 — Proof gate

| ID | Issue | Files |
|----|-------|-------|
| G1 | Empty objdiff stdout counted as zero diff | `source_parity_synthesize.parse_objdiff_report` |
| G2 | objdump fallback in `is_proven_zero` | `match_cache.py`, dump authority |
| G3 | Compile ok when stale object exists | `package_verify`, MSVC helpers |
| G4 | Byte-emitter denylist gaps (`_asm`, MASM db/dw) | `source_dump.looks_like_byte_emitter` |

### P1 — One analysis + faster decompile

| ID | Issue | Files |
|----|-------|-------|
| G5 | Inventory `-deleteProject` throws analysis away | `source_parity_one_shot.stage_inventory` |
| G6 | ghidrecomp re-analyzes from scratch | `ghidra_analysis.py`, frontdoor |
| G7 | `thread_count=2` hardcoded | `batch_decompile.py`, MCP schema |
| G8 | Reconstruct does not write facts this run | frontdoor / pipeline |

### P2 — Fresh-run I/O

| ID | Issue | Files |
|----|-------|-------|
| G9 | Silent sibling JSONL auto-load | `frontdoor.run_dump_source` |
| G10 | Cache key missing analysis-image digest | `match_cache.py` |
| G11 | Cache hit emits path-only rows | match scripts, synthesize |
| G12 | Ladder denominator can shrink | proof ladder / gates |

### P3 — Throughput (still full coverage)

| ID | Issue | Files |
|----|-------|-------|
| G13 | Always dual advisory + Port write | `--dump-layers` |
| G14 | Shared WINEPREFIX false mismatches | docs, per-worker prefixes |
| G15 | Exhaustive synth wall time | workers, compile cache, timings |
| G16 | USB work-dir I/O | use local SSD; archive after |

## Done when

- [x] One analysis receipt; inventory + decompile reuse it (`stage-timings` shows single analyze wall)
- [x] Decompile threads configurable; default > 2 on multi-core hosts
- [x] Fresh dump rejects undeclared leftover JSONL; receipts include `sourceText`
- [x] `is_proven_zero` fail-closed; tests for G1–G4
- [x] CRITICAL_PATH separates fresh runs from operator resume/dump-only
- [ ] Pre-synth wall down without dropping inventoried functions (measure on cold host after U2–U3; G15 remains)

## Related plans

[2026-07-13-feat-unified-source-parity-recovery.md](2026-07-13-feat-unified-source-parity-recovery.md) — product fold-in history. **This file** is the active perf/idempotency tracker. Embed `sourceText` and dump batch I/O are landed here.
