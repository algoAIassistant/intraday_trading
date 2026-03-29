# Family Branch Registry: failed_opening_drive_and_reclaim

This file is the single source of truth for all branches in this family.
Update it whenever a branch is created, advanced, closed, or archived.

---

## Status definitions

| Status | Meaning |
|--------|---------|
| `active` | Branch is currently being worked. Phase is open and in progress. |
| `promoted` | Branch passed all research phases. Frozen survivor exists. Eligible for engineering. |
| `closed_no_survivor` | Branch completed but no edge survived. Closed with a summary note. |
| `archived_reference_only` | Moved to `9_0_archive/retired_research_variants/`. Not active. Kept for context. |

---

## Registry

### Branch: family_root

```
branch_name:        family_root
parent_branch:      (none — this is the family entry point)
status:             active
phase:              phase_r0 → phase_r1 (phase_r0 closed go)
hypothesis_delta:   (baseline — no modification from family hypothesis)
promotion_reason:
closure_reason:
archive_location:
```

---

### Branch: phase_r1__parent_001__naive_failure_through_open

```
branch_name:        phase_r1__parent_001__naive_failure_through_open
parent_branch:      family_root
status:             active
phase:              phase_r1
hypothesis_delta:   Tests whether price reclaiming session_open after a directional 30-min drive
                    produces above-baseline returns. No magnitude filter applied.
promotion_reason:
closure_reason:
archive_location:
```

**Result summary (2026-03-25, 111 tickers, 2025-07-01 to 2025-12-31):**
- drive_up failed: mean=-0.130%, win=47.5% vs baseline -0.099% → NO LIFT
- drive_down failed: mean=+0.019%, win=48.8% vs baseline -0.098% → MARGINAL (+0.117%)
- Large drive_down failures (>= 2%): mean=+0.289%, win=53.8%, t=1.51 (not yet significant)
- Projected at 300 tickers: t≈2.48 (would be significant). Definitive run pending full cache build.

---

### Branch: phase_r1__parent_002__large_drive_down_early_reclaim

```
branch_name:        phase_r1__parent_002__large_drive_down_early_reclaim
parent_branch:      phase_r1__parent_001__naive_failure_through_open
status:             active
phase:              phase_r1
hypothesis_delta:   Restricts to large downward drives (magnitude >= 2%) that reclaim session_open.
                    Optionally filters for early reclaim events (reclaim within ~60 min of drive end).
                    Derived from parent_001 magnitude breakdown which showed signal only at >= 2%.
promotion_reason:
closure_reason:
archive_location:
```

**Status (2026-03-25):** DEFINITIVE RUN COMPLETE. Signal confirmed. Narrowed to child_001. Phase_r2 closed.

**Definitive results (259 tickers, 2025-07-01 to 2025-12-31):**
- large_drive_down__reclaimed__all: n=690, mean=+0.318%, win=50.7%, **t=2.33** (p<0.05)
- vs unconditional drive_down baseline: -0.104%, 47.5% → +0.422% mean lift, +3.2% win improvement
- Early reclaim (<=60 bars): n=132, mean=+0.795%, win=56.1% — stronger signal, smaller n
- Drive continued (no reclaim): n=2126, mean=-1.443% (strong opposing momentum)

Phase_r2 completed 2026-03-25 — NARROWED ALIVE.
Parent_002 does not advance to phase_r3. Signal is regime-dependent and price-tier specific.
child_001 spawned with explicit $5-20 price filter and non-bearish regime gate.

---

### Branch: parent_002__child_001__price_filtered_regime_gated

```
branch_name:        parent_002__child_001__price_filtered_regime_gated
parent_branch:      phase_r1__parent_002__large_drive_down_early_reclaim
status:             promoted
phase:              phase_r4 complete — all checks passed — V1 promoted
hypothesis_delta:   Adds price filter ($5-20 session open) and market regime gate (non-bearish)
                    to parent_002. Derived from phase_r2 finding that signal lives exclusively
                    in $10-20 stocks and completely inverts in bearish market months.
promotion_reason:   V1 (any reclaim, no stop, hold to close) passed all 7 phase_r4 robustness
                    checks: survives 15bp roundtrip slippage (t=2.56), OOS 2025 t=3.96,
                    concentration top-10=44.9%, tail p5=-5.13%, 5/15 negative months (33%),
                    15:00 exit alive (t=2.08). GO verdict 2026-03-25.
closure_reason:
archive_location:   frozen_survivors/frozen_survivor__child_001_v1__failed_opening_drive_and_reclaim__2026_03_25.md
```

**child_001 locked validation result (2026-03-25, 166 tickers, 2024-03-25 to 2025-12-31):**
- reclaimed__all: n=873, mean=+0.482%, win=53.0%, **t=3.71** (7 bearish months excluded)
- early_reclaim (<=60 bars): n=166, mean=+1.219%, win=61.5%, t=2.87 (stronger early signal)
- Concentration: top-10 = 44.9%, 62.5% tickers positive (improved vs phase_r2 6-month cut)
- No inversion month across 21-month non-bearish window
- Regime filter validated on 7 bearish months (vs 1 in original phase_r2)
- **VERDICT: SIGNAL CONFIRMED — advancing to phase_r3**

**Phase_r3 formalization result (2026-03-25):**
- 7 variants tested: varying stop type, profit target, and entry timing restriction
- **WINNER: V1** (any reclaim, no stop, hold to close) — t=+3.71, mean=+0.482%, win=53.0%
- Critical finding: structural stop (session_open) has 95.1% stop-out rate — incompatible with signal
- Hard stop -1.5% drops t to 1.85 — also damaging; signal requires holding through intraday noise
- V4 (early reclaim only, no stop): t=+2.87, mean=+1.219% — noted for phase_r4 sub-filter test
- **Formal candidate V1: enter at reclaim bar close, no stop, no target, exit at session close**
- Gross expectancy: +0.482% per trade (no slippage applied)
- **VERDICT: PHASE_R3 COMPLETE — advancing to phase_r4**

**Phase_r4 robustness result (2026-03-25):**
- 7 dimensions tested: slippage, OOS split, concentration, tail, exit time, V1 vs V4
- Slippage: V1 alive at 15bp roundtrip (t=2.56). Breakeven >15bp.
- OOS: V1 OOS 2025 mean=+0.640%, t=3.96 — STRONGER than IS. Not an in-sample artifact.
- Concentration: top-10 = 44.9%, 80 of 128 tickers positive (62.5%). Acceptable breadth.
- Tail: p5=-5.13%, worst event WOLF -22.47% (news outlier), 5/15 negative months (33%)
- Exit time: 15:00 exit mean=+0.249%, t=2.08. Last hour contributes; 15:59 preferred.
- V4 (early only): viable sub-filter. OOS mean=+1.646%, survives 15bp slippage.
- **All 7 checks PASSED. GO verdict issued 2026-03-25.**
- **VERDICT: PHASE_R4 COMPLETE — V1 PROMOTED. Awaiting user authorization for frozen_survivors/.**

---

## How to add a new branch entry

Copy the template below and fill in all fields.
Leave `promotion_reason`, `closure_reason`, and `archive_location` blank until they apply.

```
branch_name:        <plain_english_name>
parent_branch:      <name_of_direct_parent_branch>
status:             active | promoted | closed_no_survivor | archived_reference_only
phase:              phase_r0 | phase_r1 | phase_r2 | phase_r3 | phase_r4 | phase_e0_to_e2
hypothesis_delta:   <what is different from the parent hypothesis — one sentence>
promotion_reason:   <what passed and why — fill when status = promoted>
closure_reason:     <what failed and what it implies — fill when status = closed_no_survivor>
archive_location:   <path in 9_0_archive — fill when status = archived_reference_only>
```

---

## Rules for this registry

- Every branch that exists as a folder must have an entry here.
- A branch without a registry entry is a lineage violation.
- Do not delete entries. If a branch is closed, update the status and fill the closure fields.
- Entries are append-only. Add new entries below existing ones.
- This file is updated by the user or by Claude Code on user instruction — not autonomously.
