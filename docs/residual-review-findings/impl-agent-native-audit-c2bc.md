---
branch: impl/agent-native-audit-c2bc
plan: docs/plans/2026-05-24-lfg-agent-native-audit-c2bc.md
audit: docs/audits/2026-05-24-agent-native-audit.md
---

# Residual findings — agent-native audit (P1+)

From [2026-05-24 agent-native audit](../audits/2026-05-24-agent-native-audit.md). Implementation is **out of scope** for the audit PR; track here for follow-up slices.

## P1 — high impact, low–medium effort

| ID | Area | Action | Principle |
|----|------|--------|-----------|
| P1-1 | `program_metadata.collect_project_context()` | Add `analysisComplete`, compact `checkoutSummary`; inject slim context on errors | Context injection |
| P1-2 | MCP server | Implement **`prompts/get`** (9 prompts listed; content exists) | Discovery + prompt-native |
| P1-3 | Mutating tool responses | Add **`uiVisibility` / `guiHint`** footer | UI integration |
| P1-4 | Proxy | Forward **`x-agentdecompile-project-path`** header | Shared workspace |

## P2 — CRUD and surface

| ID | Area | Action |
|----|------|--------|
| P2-1 | `manage-data-types` / new tool | Enum CRUD (`manage-enums` or enum modes) |
| P2-2 | `manage-symbols` | `delete_label` / remove label mode |
| P2-3 | Curated tool surface | Advertise list/search primitives; demote `search-everything` / `get-function` to `full` |
| P2-4 | Discovery | `.cursor/commands/help.md` or `/capabilities` slash command |

## P3 — docs / hygiene

| ID | Action |
|----|--------|
| P3-1 | Document dual-JVM + checkin-before-GUI-reload in README |
| P3-2 | Fix or remove **`suggest`** stub |
| P3-3 | Fail hard on `import-binary` temp ProjectManager fallback |

## Ship gate (audit plan R4)

- [ ] Stage `docs/audits/2026-05-24-agent-native-audit.md`, plan, residual doc, AGENTS.md cross-link
- [ ] Push `impl/agent-native-audit-c2bc` and open PR (do not include unrelated `_version.py` / lockfile churn)
