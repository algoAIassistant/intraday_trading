# Research Rules

Scope: all work inside `1_0_strategy_research/`.

---

## Active track

Default track is `intraday_same_day`.
Do not switch to `swing_secondary` unless the user explicitly requests it.

## Phase order

Work must follow this sequence. Do not skip forward.

1. `phase_r0` — intraday baseline (natural same-day behavior)
2. `phase_r1` — conditional behavior (one condition at a time)
3. `phase_r2` — structural validation (stability by year, window, bucket, context)
4. `phase_r3` — strategy formalization (entry, exit, stop, profit-taking, time exit)
5. `phase_r4` — robust validation (slippage, concentration, tails, out-of-sample)

Engineering (`phase_e0_to_e2`) begins only after phase_r4 survival.

## Intraday flagship constraints

- Same-day entry and same-day exit only.
- Flat by close. No overnight positions.
- Opening minutes are a variable to test, not a universal assumption.
- Stock-level observables come first. Market context (SPY/QQQ) is secondary during early discovery.

## Lineage model

Every research branch must follow this model:

```
track → family → parent → child → grandchild → further descendants
```

- No artificial cap on branch count.
- Parent/child relationship must be explicit in folder names and lineage notes.
- Do not collapse lineage to save space.

## Output preservation

- Do not overwrite prior outputs. Extend or branch instead.
- Preserve lineage notes when extending a family.
- Document what changed and why when creating a new child or grandchild.

## No-survivors path

If a phase, family, or branch produces no valid survivors:

- Mark it closed explicitly — do not leave it ambiguous or in-progress.
- Write a brief summary note: what was tested, why it failed, and what the failure implies.
- Move the folder or outputs to `9_0_archive/retired_research_variants/` and update any lineage notes that reference it.
- Do not delete — archive with context so future sessions can learn from it.
- Do not silently start a new branch without acknowledging the closed one.

## General research behavior

- Inspect repo state before proposing edits.
- Do not invent strategy logic — follow market behavior → statistical evidence → structural validation.
- Do not mix research and engineering code in the same file or folder.
- Prefer deterministic, cache-first workflows.
- Do not leave temporary or debug files with vague names.
