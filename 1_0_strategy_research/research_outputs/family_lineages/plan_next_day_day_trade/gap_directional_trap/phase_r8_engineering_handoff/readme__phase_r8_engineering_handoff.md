# readme__phase_r8_engineering_handoff

folder: phase_r8_engineering_handoff
family: gap_directional_trap
track:  plan_next_day_day_trade
date:   2026-03-27

---

## What this folder contains

This folder is the research-to-engineering handoff package for the
gap_directional_trap family.

It contains the complete specifications for two validated deployable variants
that have passed all research phases (r0 through r6).

---

## Files in this folder

| file | purpose |
|------|---------|
| handoff_doc__gap_directional_trap__phase_r8__2026_03_27.md | main engineering entry point; full human-readable spec for both variants |
| variant_spec__gap_directional_trap__candidate_1_v1__phase_r8__2026_03_27.yaml | machine-friendly spec for the preferred production variant |
| variant_spec__gap_directional_trap__candidate_2_v1__phase_r8__2026_03_27.yaml | machine-friendly spec for the backup fixed-% variant |
| readme__phase_r8_engineering_handoff.md | this file |

---

## Start here

Read `handoff_doc__gap_directional_trap__phase_r8__2026_03_27.md` first.

That document defines:
- what the variants are and why they were promoted
- exact entry, stop, target, cancel, and exit formulas for each variant
- TOS manual workflow
- data dependencies
- required output fields for the nightly signal pack
- what engineering needs to build next
- what was deliberately not built

---

## Upstream research context

```
phase_r0:  tradable universe foundation (shared master universe)
phase_r1:  market context model (bearish / neutral / bullish labels)
phase_r2:  gap_directional_trap parent baseline
phase_r3:  child isolation (gap_up_cl_low_020 child selected)
phase_r4:  structural validation (bearish × medium/large grandchildren promoted)
phase_r5:  execution template research (range_proxy_75pct and fixed_3pct stops)
phase_r6:  deployable variant validation (BOTH candidates promoted)
phase_r8:  this folder (engineering handoff)
```

Phase_r7 (ranking layer) is deferred.
No competing variants from other families exist yet.
Engineering can proceed with candidate_1 as the sole production variant.

---

## Engineering-side counterpart

```
2_0_agent_engineering/integrated_strategy_modules/plan_next_day_day_trade/
  gap_directional_trap__bearish_medium_large__candidate_1_v1/
    engineering_module_manifest__gap_directional_trap__candidate_1_v1.md
```
