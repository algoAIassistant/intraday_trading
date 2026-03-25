# Protected Files Rules

Scope: files that must not be silently modified, overwritten, or deleted.

---

## Protected files

The following files are protected. Do not edit them without explicit user instruction.

| File | Reason |
|------|--------|
| `CLAUDE.md` | Repo constitution. Changes require explicit user authorization. |
| `.claude/rules/research_rules.md` | Scoped research operating rules. |
| `.claude/rules/engineering_rules.md` | Scoped engineering operating rules. |
| `.claude/rules/naming_rules.md` | Naming standards. |
| `.claude/rules/protected_files_rules.md` | This file. |
| `.claude/settings.local.json` | Claude Code local permissions config. |

## What "protected" means

- Do not edit these files as a side effect of another task.
- Do not rewrite them to make a task easier.
- Do not silently remove sections.
- If a task requires changing one of these files, stop and confirm with the user first.

## Root infrastructure files

`CLAUDE.md` and `.gitignore` are root infrastructure. Both Write and Edit are denied in `settings.local.json`.
Do not modify either as a convenience step during unrelated work.

## Engineering side

`2_0_agent_engineering/` is gated. Both Write and Edit are denied until the user explicitly opens engineering work.
No strategy logic, config, or module may be created there without a frozen research survivor as the justification.

## Lineage outputs

Research outputs are append-only unless the user explicitly requests overwrite.

- Do not delete prior outputs when extending a study.
- Do not rename lineage folders without updating all references and notifying the user.
- Frozen survivors in `integrated_strategy_modules/` must not be modified without explicit user instruction.

## Shared universe files

Files in `0_1_shared_master_universe/` (symbol lists, calendars, reference configs) are shared across the entire ecosystem.
Changes here affect all tracks and all phases.
Confirm with the user before modifying shared universe files.

## Archive

`9_0_archive/` is read-only reference material. Both Write and Edit are denied in `settings.local.json`.
Do not delete archive files.
Do not move active work into archive without user instruction.
When closing a failed research branch, move it to archive with a summary note — do not delete it.
