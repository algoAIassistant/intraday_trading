# Project Master: Research Workflow

---

## Core principle

Strategy is formed after statistical evidence, not before.

The correct direction is:

```
market behavior -> statistical evidence -> structural validation -> strategy formalization -> robust validation -> engineering
```

Never reverse this. Do not start with an idea and backfill evidence.

---

## Layer logic

The research machine operates in layers. Each layer depends on the one below it.

**Data layer**
Raw price, volume, and market data. Cached locally. Not re-fetched if already present.
Lives in: `1_0_strategy_research/research_data_cache/`

**Research layer**
Exploratory studies on raw behavior — baselines, conditionals, structural patterns.
Lives in: `1_0_strategy_research/research_source_code/` and `research_outputs/`

**Strategy formation layer**
Formalization of confirmed edges into defined strategies with explicit rules.
Lives in: `research_source_code/strategy_formalization/` and `research_outputs/formalization/`

**Module layer**
Frozen, validated strategy variants that survived all research phases.
Lives in: `research_source_code/strategy_families/` → and later `2_0_agent_engineering/integrated_strategy_modules/`

**System layer**
Production runtime: dispatch, ranking, risk, execution.
Lives in: `2_0_agent_engineering/engineering_source_code/`
Requires at least one frozen module to exist first.

---

## Active intraday phase flow (intraday_same_day)

Phases must be followed in order. Do not skip forward.

**phase_r0 — intraday baseline**
Understand natural same-day price behavior without conditions.
Question: what does this stock type do from open to close, unconditionally?

**phase_r1 — conditional behavior**
Test one condition at a time against the baseline.
Question: does this condition produce a measurable, repeatable shift in behavior?

**phase_r2 — structural validation**
Keep only stable uplift. Test by year, window size, bucket, and market context.
Question: is the conditional edge structurally stable or fragile?

**phase_r3 — strategy formalization**
Define exact entry, exit, stop, profit-taking rule, and time-based exit.
Question: can this edge be expressed as a complete, executable strategy?

**phase_r4 — robust validation**
Validate stability, slippage sensitivity, ticker concentration, tail behavior, and out-of-sample.
Question: does this strategy survive realistic conditions?

**phase_e0_to_e2 — engineering**
Implement only frozen survivors. Engineering starts here and not before.

---

## No-survivors path

If a phase or branch produces no valid survivors:

- Close it explicitly. Write a brief note: what was tested, why it failed, what it implies.
- Move to `9_0_archive/retired_research_variants/` with the summary attached.
- Update any lineage notes that reference the closed branch.
- Do not start a new branch without acknowledging the closed one first.
