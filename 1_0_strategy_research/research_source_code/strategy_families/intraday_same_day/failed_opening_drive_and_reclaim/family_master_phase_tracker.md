# Family Phase Tracker: failed_opening_drive_and_reclaim

Update this file when a phase opens, produces artifacts, or closes.

---

## Current family state

```
family_status:        active
current_phase:        phase_r0
last_updated:         2026-03-24
active_branch:        (none — phase_r0 not yet started)
```

---

## phase_r0 — intraday baseline

**Purpose:** Understand natural same-day price behavior for the stock types relevant to this family, without applying any conditions.

**Status:** `not_started`

**Required artifacts before closing phase_r0:**
- Baseline distribution of same-day returns for target universe
- Characterization of intraday behavior around early session drives (no filter applied)
- Summary note confirming whether a non-uniform pattern is observable at the family level

**Closure rule:**
Phase_r0 is complete when the baseline is documented and a clear go/no-go decision is made for phase_r1.
If the baseline shows no non-uniformity worth investigating, close the family here as `closed_no_survivor`.

---

## phase_r1 — conditional behavior

**Purpose:** Test the failure-and-reclaim condition against the phase_r0 baseline. One condition at a time.

**Status:** `locked — requires phase_r0 completion`

**Required artifacts before closing phase_r1:**
- At least one conditional test with clearly defined condition logic
- Comparison of conditioned returns vs. unconditional baseline
- Summary note: does the condition produce measurable lift?

**Closure rule:**
Phase_r1 is complete when at least one condition shows measurable, non-trivial lift — or when all reasonable conditions have been tested and none shows lift.
If no lift found, close as `closed_no_survivor`.

---

## phase_r2 — structural validation

**Purpose:** Confirm that any edge found in phase_r1 is stable across years, windows, buckets, and market contexts.

**Status:** `locked — requires phase_r1 completion`

**Required artifacts before closing phase_r2:**
- Year-by-year breakdown of the conditional edge
- Bucket breakdown (cap tier, volume tier, or other relevant segmentation)
- Market context overlay (SPY/QQQ regime as a validation check, not a primary filter)
- Summary note: structurally stable or fragile?

**Closure rule:**
Phase_r2 is complete when stability is confirmed across multiple dimensions — or when the edge is shown to be concentrated in a single period or bucket.
If concentrated or unstable, close as `closed_no_survivor`.

---

## phase_r3 — strategy formalization

**Purpose:** Define a complete, executable strategy from the validated edge.

**Status:** `locked — requires phase_r2 completion`

**Required artifacts before closing phase_r3:**
- Entry rule (exact condition, timing, direction)
- Exit rule (target, time-based, or structural)
- Stop rule (hard stop or structural stop)
- Profit-taking rule (partial or full)
- Time-based exit rule (latest allowed exit before close)
- Initial expectancy estimate on in-sample data

**Closure rule:**
Phase_r3 is complete when all five rule components are defined and the strategy produces positive expectancy in-sample without overfitted parameters.
If no viable rule set can be produced, close as `closed_no_survivor`.

---

## phase_r4 — robust validation

**Purpose:** Stress-test the formalized strategy under realistic conditions.

**Status:** `locked — requires phase_r3 completion`

**Required artifacts before closing phase_r4:**
- Slippage sensitivity analysis
- Ticker concentration check (edge not driven by a handful of names)
- Tail behavior analysis (loss distribution, worst drawdown periods)
- Out-of-sample test results
- Final go/no-go recommendation

**Closure rule:**
Phase_r4 is complete when all five stress tests are documented.
If the strategy fails any critical stress test, close as `closed_no_survivor`.
If all tests pass and the user approves, status becomes `promoted` and the variant moves to `frozen_survivors/`.

---

## No-survivor closure path

If any phase produces a `closed_no_survivor` outcome:

1. Write a closure note in this file under the relevant phase section.
2. Record what was tested, what failed, and what the failure implies for future work.
3. Update `family_master_branch_registry.md` to mark affected branches as `closed_no_survivor`.
4. Move the family folder (or the closed branch) to `9_0_archive/retired_research_variants/` with the closure note attached.
5. Do not start a new family or branch without acknowledging this closure in the handoff notes.
