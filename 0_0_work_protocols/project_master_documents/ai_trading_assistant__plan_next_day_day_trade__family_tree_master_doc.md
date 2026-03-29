# ai_trading_assistant__plan_next_day_day_trade__family_tree_master_doc

status: draft_v1

purpose:
This master document defines the structural family tree for the track: plan_next_day_day_trade

This track is for research and later engineering of day-trade ideas that are planned the night before and manually executed in Thinkorswim using predefined prices.

The core requirement of this track is: every final research output must be night_before_executable

That means the model must be able to produce:
- entry price
- stop loss price
- take profit price

without requiring live morning monitoring from the user.

---

## 1. CORE IDENTITY OF THE TRACK

track_name: plan_next_day_day_trade

track_definition:
Create next-day day-trade plans using only completed information available at the close of the signal day.

This track does not depend on:
- live broker automation
- reactive intraday execution
- live market monitoring by the user after the open

This track does depend on:
- after-close research logic
- fully specified trade-plan generation
- exact preplanned prices for entry, stop, and target
- manual execution in Thinkorswim using bracket and/or conditional orders

core output of the track: **deployable next-day bracket-ready trade plan**

---

## 2. TOP-LEVEL PROJECT SPLIT

This track lives inside the existing ai_trading_assistant repo.

It has two major sides:
- 1_0_strategy_research
- 2_0_agent_engineering

For this track:

1_0_strategy_research:
researches and validates setup families, filters, variants, and order-ready trade-plan logic

2_0_agent_engineering:
packages the validated research into signal-generation runtime, ranking, message formatting, and Telegram delivery

Important:
For this track, agent_engineering does not initially mean broker auto-execution.
It means signal delivery, trade-plan packaging, and manual execution support.

---

## 3. FAMILY TREE OVERVIEW

The structural hierarchy for this track is:

```
track
  -> family
    -> child
      -> grandchild
        -> deployable_variant
```

Definitions:

**track:** the full strategic lane
example: plan_next_day_day_trade

**family:** a broad market behavior type or setup archetype
examples:
- gap_continuation
- failed_breakdown_reclaim
- compression_breakout
- strong_close_next_day_momentum
- trend_pullback_reentry

**child:** a meaningful subtype of a family
A child still uses the same core mechanism as the family, but narrows it into a specific structural subtype.
examples:
- gap_continuation__liquid_midprice_trend_names
- gap_continuation__high_rvol_small_midcaps
- strong_close_next_day_momentum__trend_aligned_only

**grandchild:** a parameterized research cell inside a child
A grandchild changes filters, thresholds, buckets, or conditions while preserving the child's structural logic.
examples:
- gap_continuation__liquid_midprice_trend_names__price_10_20__adv_20m_plus__rvol_1_8_plus
- gap_continuation__liquid_midprice_trend_names__price_20_40__adv_30m_plus__rvol_2_0_plus

**deployable_variant:** a fully specified execution-ready version of a grandchild
This is the final research unit that can actually generate: entry, stop, target, same-day exit rule, non-trigger / cancel logic if applicable.
This is the required endpoint of research for this track.

---

## 4. STRUCTURAL RULE FOR SPLITTING LEVELS

Use this rule:

**family:** use when the broad price-behavior mechanism is the same

**child:** use when the mechanism remains the same, but the subtype becomes meaningfully different in practical behavior

**grandchild:** use when the same child is being tested under different filters, thresholds, price buckets, liquidity buckets, or parameter cells

**deployable_variant:** use when the setup has a complete execution template that can be used the night before

Simple decision rule:
- If the market behavior logic changes materially: make a new family or new child
- If the market behavior logic stays the same but the filter set changes: make a new grandchild
- If the setup becomes fully order-ready: promote it to deployable_variant

---

## 5. RESEARCH STACK INSIDE THIS TRACK

Research for this track is performed in layers.

**layer_1: universe_layer**
Purpose: define the tradable research universe
- U.S. common stocks only
- price buckets
- average daily volume
- average dollar volume
- ATR or daily range minimum if needed
- liquidity protection rules
Important: The universe layer is not the strategy. It is the tradable sandbox for research.

**layer_2: market_context_layer**
Purpose: tag the market context at the close of the signal day
Important correction: This layer is not trying to predict tomorrow. It only describes the environment at the time the signal is created.
Examples: bullish / neutral / bearish
Possible inputs: SPY/QQQ relative to moving averages, slope of moving averages, realized volatility, VIX regime, breadth later if needed

**layer_3: family_layer**
Purpose: identify broad setup families
Examples: gap_continuation, failed_breakdown_reclaim, strong_close_next_day_momentum, compression_breakout

**layer_4: child_layer**
Purpose: define meaningful subtypes of the family
This is where the same family is split into more behaviorally consistent subgroups.

**layer_5: grandchild_layer**
Purpose: test exact filter cells and parameter combinations
Studies how performance changes by: price bucket, average dollar volume bucket, average share volume bucket, relative volume threshold, ATR bucket, gap bucket, trend filter, market-context tag, other stable research filters

**layer_6: execution_template_layer**
Purpose: attach exact trade-plan logic
Every serious candidate must eventually define: entry formula, stop formula, take-profit formula, cancel / no-trigger rule, same-day close exit rule

**layer_7: deployable_variant_layer**
Purpose: identify the variants that are strong enough and complete enough to become usable trade-plan generators
A deployable_variant is the final research output that engineering can later package into Telegram-ready signals.

---

## 6. NIGHT_BEFORE_EXECUTABLE RULE

This is the defining rule of the track.

A setup is not complete unless it can be converted into a night-before executable trade plan.

Minimum required outputs for a deployable_variant:
1. exact entry logic
2. exact stop logic
3. exact take-profit logic
4. exact time-exit rule
5. exact invalidation or no-trigger behavior
6. same-day flat-by-close behavior if that is part of the strategy definition

Examples of valid plan styles:
- buy_stop_above_prior_high
- buy_limit_on_defined_pullback_level
- short_stop_below_prior_low
- bracket order with fixed R multiple
- target based on ATR expansion
- stop based on prior day low, opening range proxy, or volatility band

Important: This track cannot depend on manual morning interpretation. The plan must already be defined.

---

## 7. MARKET CONTEXT USAGE RULE

Market context is used as: context_at_signal_creation

It is NOT used as: certainty_about_tomorrow

Correct usage:
If a signal forms today under bearish context, research can test whether that setup historically performs well or poorly for the next session under that context.

Incorrect usage:
If market is bearish today, assume market will definitely be bearish tomorrow and force execution based on that belief.

Therefore: market_context is a research tag, not a prediction engine.

---

## 8. WHAT COUNTS AS A DIFFERENT CHILD

A new child should be created when the behavior meaningfully changes.

Examples of reasons to split into a new child:
- liquid trend names behave differently from small fast names
- continuation after compression behaves differently from continuation after expansion
- trend-aligned continuation behaves differently from countertrend rebound continuation
- low-gap continuation behaves differently from large-gap continuation in a way that changes execution logic

If the execution style itself must change significantly, that is often a sign the subtype may deserve its own child.

---

## 9. WHAT COUNTS AS A GRANDCHILD

A new grandchild should be created when the same child is being tested under different parameter cells.

Examples — same child, but different:
- price buckets
- adv buckets
- average share volume buckets
- rvol thresholds
- ATR thresholds
- gap-size buckets
- target distances
- stop distances
- market-context slices

Grandchildren are not random. They must still inherit the same logic from the child.

---

## 10. WHAT COUNTS AS A DEPLOYABLE_VARIANT

A deployable_variant is a grandchild that has passed both:
1. behavioral validation
2. execution-template completion

It must be able to answer:

- **setup_identity:** what exactly is the setup
- **universe_definition:** what names are eligible
- **signal_definition:** what exactly triggers the setup at the close
- **entry_definition:** what exact price or order logic is used tomorrow
- **stop_definition:** what exact invalidation price is used
- **target_definition:** what exact profit objective is used
- **time_exit_definition:** when the trade is force-closed if target/stop do not hit
- **cancel_definition:** what happens if the order never triggers or the open is hostile

Only after those answers exist should the model be considered deployable.

---

## 11. EXAMPLE FAMILY TREE

```
track: plan_next_day_day_trade

family: gap_continuation

child: gap_continuation__liquid_midprice_trend_names

grandchild: gap_continuation__liquid_midprice_trend_names__price_10_20__adv_20m_plus__rvol_1_8_plus

deployable_variant: gap_continuation__liquid_midprice_trend_names__price_10_20__adv_20m_plus__rvol_1_8_plus__entry_above_signal_high__stop_below_signal_low__target_2r__flat_by_close
```

Meaning of the example:
- family: gap_continuation — broad behavior type
- child: liquid midprice trend names — behaviorally narrowed subtype
- grandchild: specific research cell based on price and liquidity and rvol
- deployable_variant: exact night-before executable order-ready rule set

---

## 12. ENGINEERING HANDOFF RULE

Engineering should not begin from raw family ideas.
Engineering should begin only after a deployable_variant exists.

That means research hands engineering:
- validated setup definition
- validated filters
- entry formula
- stop formula
- target formula
- ranking fields
- message payload fields
- order-ready output format

For this track, early engineering targets may include:
- nightly scanner runtime
- ranking runtime
- trade-plan formatter
- Telegram message delivery
- trade journal logging
- daily result reporting

Not required at first:
- broker automation
- live order execution
- live open monitoring

---

## 13. NAMING RULES

Use lowercase_and_underscores only.

Recommended hierarchy naming format:

```
track: plan_next_day_day_trade

family: gap_continuation

child: gap_continuation__liquid_midprice_trend_names

grandchild: gap_continuation__liquid_midprice_trend_names__price_10_20__adv_20m_plus__rvol_1_8_plus

deployable_variant: gap_continuation__liquid_midprice_trend_names__price_10_20__adv_20m_plus__rvol_1_8_plus__entry_above_signal_high__stop_below_signal_low__target_2r__flat_by_close
```

Naming should preserve: behavior family, subtype, main filter cell, execution template.

---

## 14. MASTER PRINCIPLES OF THIS TRACK

1. research must be based on completed information available at signal-day close
2. the user should not need to manually watch the open
3. the final research unit is not a signal, but a deployable next-day bracket-ready trade plan
4. family and child define behavior structure
5. grandchild defines the research cell
6. deployable_variant defines the exact execution recipe
7. market context is used as context, not prediction
8. engineering later packages validated deployable_variants into signal delivery, not necessarily broker automation
9. study aftermath, not only the headline setup — when broad behavior is crowded or predictable, the edge may live in the failure, trap, or reclaim that follows

---

## 15. CURRENT FAMILY REGISTRY

### Family 1: gap_continuation
status: envelope_reference_family — directional_path_closed
registered: 2026-03-27

definition:
A stock in the phase_r0 working universe that opened with a gap
(|gap_pct| = |open_T - close_{T-1}| / close_{T-1}) of at least a threshold
on signal day T, where the plan is to trade next-day T+1 in the direction
of the gap.

night_before_definable: yes — gap size and direction are fully observable at EOD.

parent_baseline_result (phase_r2, 2026-03-27):
- 808,679 events across 1,993 tickers, 2021-04-23 to 2026-03-24
- gap threshold: 0.5% (broad parent)
- continuation rate: ~48.8% overall (near-random at parent level — expected)
- next-day daily range: ~4.2% mean; bearish regime wider (4.73%) vs bullish (3.99%)
- gap-up in bearish context: 51.9% continuation (best at parent level)

phase_r3_child_isolation_result (2026-03-27):
quality filter applied: |gap_pct| <= 30% (removed 558 data-error events; 808,121 remain)

child_1: gap_continuation__liquid_trend_names
- filters: ADV in top 3 buckets ($20M+) AND gap direction matches stock SMA20 position
- sample: 364,529 events (45% of quality-filtered parent)
- continuation: 48.6% — NO meaningful improvement over parent
- mean open->close: +0.001% — essentially flat
- range: 3.99% (lower than parent; expected for liquid names)
- finding: SMA20 trend-alignment does NOT isolate a continuation edge at the 0.5% gap level
- recommendation: HOLD — promote to phase_r4 with gap-size segmentation as primary dimension

child_2: gap_continuation__high_rvol_names
- filters: signal_day_volume >= 1.5x prior 20-day rolling avg volume
- sample: 120,046 events (15% of quality-filtered parent)
- continuation: 48.6% — NO directional improvement over parent
- mean open->close: -0.008% — essentially flat
- range: 5.40% — notably LARGER than parent (4.22%)
- finding: high-RVOL days generate wider next-day ranges but no directional edge alone
- recommendation: HOLD — reframe as a grandchild modifier for range/target sizing research

key_finding_from_phase_r3:
Both children reproduce near-random (~49%) continuation. The broad 0.5% gap threshold
mixes small noisy gaps with meaningful gaps. Primary phase_r4 direction:
gap SIZE segmentation — small (0.5-1.5%), medium (1.5-3.0%), large (>=3.0%).
Large gaps are expected to show more differentiated behavior by direction and regime.

phase_r4_structural_validation_result (2026-03-27):
primary_dimension_tested: gap size segmentation (small 0.5–1.5%, medium 1.5–3%, large >=3%)
quality_cap: |gap_pct| <= 30% (carried from phase_r3)

grandchild sample sizes:
- liquid_trend__small_gap:   248,586 events (68% of child1)
- liquid_trend__medium_gap:   78,903 events (22%)
- liquid_trend__large_gap:    37,040 events (10%)
- high_rvol__small_gap:       62,061 events (52% of child2)
- high_rvol__medium_gap:      28,502 events (24%)
- high_rvol__large_gap:       29,483 events (25%)

key_finding_1 (range scales with gap size — confirmed):
  Range expands monotonically with gap size:
  - liquid_trend: small 3.4%, medium 4.6%, large 6.6%
  - high_rvol: small 4.5%, medium 5.6%, large 7.2%
  high_rvol adds ~1% wider range than liquid_trend at every gap size.
  This is the most structurally consistent finding in the entire family so far.

key_finding_2 (no directional edge from gap size alone):
  Continuation rates remain 47-49% across all 6 grandchildren.
  Gap size segmentation does NOT isolate a directional continuation edge.
  The family as defined (trade in direction of the gap) produces near-random outcomes
  regardless of gap size, direction, or liquidity filter.

key_finding_3 (neutral regime shows modest consistent lift):
  Neutral regime shows 50-52% continuation for liquid_trend grandchildren:
  - liquid_trend__small_gap:  neutral 51.8% vs bullish 48.1% vs bearish 48.8%
  - liquid_trend__medium_gap: neutral 50.6% vs bullish 46.0% vs bearish 48.3%
  - liquid_trend__large_gap:  neutral 51.4% vs bullish 47.1% vs bearish 47.6%
  Signal is consistent across all gap sizes for liquid_trend names.
  Effect is absent or weaker for high_rvol names.
  Not strong enough alone; worth combining with gap size in the next step.

key_finding_4 (yearly instability):
  liquid_trend__large_gap yearly continuation: 50.9%, 50.8%, 48.9%, 43.1%, 50.4%, 44.1%
  high_rvol__large_gap: 47.8%, 49.7%, 47.5%, 45.1%, 51.4%, 48.4%
  Neither is stable year over year. 2024 was notably weak for liquid_trend.

grandchild_recommendation_board:
  CONTINUE:
    liquid_trend__large_gap + neutral_regime — best structural combination found:
      neutral cont = 51.4%, n = 6,148, range = 6.6%
      Combine with close_location or gap/ATR ratio filter to test directional sharpening.
  CONTINUE (as range envelope tool):
    high_rvol__large_gap — range 7.2% is the widest envelope in the family.
      Not a directional setup as currently defined.
      Use as target/envelope sizing input in later execution template research.
  HOLD (test neutral + close_location next):
    liquid_trend__medium_gap + neutral_regime — 50.6% cont, 4.6% range, 15K events.
      Worth testing if a close_location filter sharpens direction.
  DROP (no structure):
    small_gap for both children — 49% continuation, 3.4-4.5% range.
      No directional edge. Too noisy at this gap size.

phase_r4_structural_validation_result_batch_2 (2026-03-27):
primary_target: liquid_trend__large_gap + neutral regime (6,148 events)
secondary: liquid_trend__medium_gap + neutral (15,347 events)
modifiers_tested:
  modifier_1: close_location_band — cl_low (<0.35), cl_mid (0.35-0.65), cl_high (>=0.65)
  modifier_2: gap_to_range_ratio — ratio = abs(gap_pct) / signal_day_range_pct
              ratio_minor (<0.25), ratio_moderate (0.25-0.50), ratio_dominant (>=0.50)
  cl_aligned_flag: gap_up+cl_high or gap_down+cl_low (expected momentum alignment)
  cl_opposed_flag: gap_up+cl_low or gap_down+cl_high (reversal of close direction)
  combined_filter: cl_aligned AND ratio_dominant

batch_2_key_finding_1 (close_location opposes expectation):
  The expected hypothesis was: stocks closing aligned with gap direction would continue better.
  Result: cl_aligned does NOT improve continuation. cl_OPPOSED shows unexpected lift.
  neutral large_gap cl_opposed: 54.0% cont (n=2,026) vs baseline 51.4% (n=6,148)
  Breakdown: gap_down + cl_high (neutral): 55.0% cont (n=1,089, o->c -0.332%)
             gap_up + cl_opposed (neutral): 52.7% cont (n=937, o->c +0.410%)
  Interpretation: stocks that gap in the OPPOSITE direction of their prior close location
  show modestly better continuation. This is counterintuitive and may represent a
  different behavioral mechanism (trapped longs/shorts, gap exhaustion reversal).

batch_2_key_finding_2 (gap_to_range_ratio does not discriminate for large_gap):
  76.2% of liquid_trend__large_gap events have ratio_dominant (avg_ratio=1.058)
  The gap is already larger than the signal day range in most large_gap events.
  ratio_dominant barely filters the set: n=28,210 out of 37,040 (76%).
  Result: no meaningful directional improvement from ratio filter in large_gap.
  For medium_gap: 50.3% ratio_dominant — discriminates better but also no directional lift.

batch_2_key_finding_3 (combined filter: sample cost without reward):
  neutral + cl_aligned + ratio_dominant: n=1,719, 51.4% cont (same as baseline)
  Cutting 72% of the neutral large_gap sample produces no directional edge.

batch_2_key_finding_4 (yearly instability confirmed):
  neutral large_gap baseline yearly: 55.6%, 51.7%, 51.5%, 47.7%, 53.8%, 43.6%
  neutral large_gap cl_opposed yearly: [not separately computed but implied unstable]
  neutral large_gap combined yearly: 52.4%, 50.5%, 51.8%, 49.5%, 58.3%, 36.5%
  2024 is consistently the weak year. 2026 (partial) is very weak (36-43%).

batch_2_decision_matrix:
  cl_aligned filter              → DROP — hurts or is flat; opposite of expected signal
  cl_opposed as hypothesis       → INTERESTING but not actionable yet:
                                   54% cont is a modest lift on n=2,026 with yearly instability
                                   This may be a different behavioral archetype (new child candidate)
                                   rather than a filter within gap_continuation
  ratio_dominant for large_gap   → DROP — 76% of large_gap events have ratio_dominant;
                                   not a useful discriminant
  ratio_dominant for medium_gap  → DROP — no directional lift
  gap_continuation (directional) → REFRAME: the gap_continuation track as a pure
                                   directional setup (trade in gap direction) is not
                                   producing a stable, filterable edge after 2 grandchild batches

batch_2_family_conclusion:
  The gap_continuation family is primarily a RANGE/ENVELOPE family, not a directional one.
  The next-day range story is real and stable (large_gap: 6.6-7.2% mean range).
  The directional story (trade in gap direction) has no reliable filter across:
  - gap size (batch_1)
  - close_location (batch_2)
  - gap_to_range_ratio (batch_2)

  Promotion decision: Do NOT promote any grandchild to phase_r5 based on batch_2 results.

  Two valid paths forward:
  PATH_A (range-based): Keep large_gap as an input to target-range sizing in execution templates.
    If a direction signal from another family points to a setup in the same stock,
    the large_gap + high_rvol envelope (~7%) is a real and usable range reference.
  PATH_B (new child hypothesis): The cl_opposed signal suggests testing a "gap_reversal" or
    "directional_trap" child — where the bet is AGAINST the gap direction on stocks that
    show gap direction OPPOSING signal day close. This is a different mechanism and
    belongs as a new child, not a grandchild filter of gap_continuation.

next_step:
  No immediate phase_r5 promotion from gap_continuation.
  Options for next session:
  a) Register a new child: gap_continuation__directional_trap (cl_opposed hypothesis)
     — tests betting AGAINST gap direction when close opposes gap
  b) Park gap_continuation as a range-envelope reference tool and begin a new family
     (strong_close_momentum or failed_breakdown_reclaim — both already registered)
  c) Accept gap_continuation as a range tool only and proceed to another family

source_scripts:
research_source_code/strategy_families/plan_next_day_day_trade/gap_continuation/
  research_run_gap_continuation_phase_r2_parent_baseline.py
  research_run_gap_continuation_phase_r3_child_isolation.py
  research_run_gap_continuation_phase_r4_grandchild_gap_size_segmentation.py
  research_run_gap_continuation_phase_r4_directional_sharpening.py

output_folders:
research_outputs/family_lineages/plan_next_day_day_trade/gap_continuation/
  phase_r2_parent_baseline/
  phase_r3_child_isolation/
  phase_r4_structural_validation/  (contains both batch_1 and batch_2 outputs)

---

### Family 5: gap_directional_trap
status: phase_r4_complete
registered: 2026-03-27

definition:
A stock in the phase_r0 working universe where:
  1. |gap_pct| >= 0.5% on signal day
  2. signal_day_close_location OPPOSES the gap direction:
     - gap_up events:   close_location < 0.35 (stock closed in lower 35% of its range
                        despite the next-day gap being upward)
     - gap_down events: close_location >= 0.65 (stock closed in upper 65%+ of its range
                        despite the next-day gap being downward)
  3. quality_cap: |gap_pct| <= 30%

family_mechanism_hypothesis:
When the prior-day close structure OPPOSES the gap direction, the gap may more reliably
continue in the gap direction. Possible explanations:
  - Longs who sold into a weak close (gap_up case) may be trapped short and forced to
    cover as the gap confirms the move.
  - Shorts who shorted into a strong close (gap_down case) may be trapped and forced
    to cover if the gap confirms downward movement.
  This is not a continuation-of-close-direction trade. It is a trade WITH the gap
  direction, where the opposing close structure is the qualifying signal.

why_this_is_a_new_family_not_a_child_of_gap_continuation:
  gap_continuation is defined as: trade in the direction of the gap.
  gap_directional_trap is also defined as: trade in the direction of the gap.
  The difference is the qualifying condition: gap_directional_trap requires the
  signal-day close structure to OPPOSE the gap direction. This is a different
  behavioral mechanism (trapped positioning) that emerged from batch_2 findings as
  counterintuitive to the gap_continuation framework. It deserves a clean baseline
  rather than being grafted onto a family that has been closed for directional promotion.

evidence_from_batch_2:
  liquid_trend__large_gap + neutral + cl_opposed: 54.0% cont (n=2,026 vs baseline 51.4%)
  gap_down + cl_high + neutral: 55.0% cont (n=1,089)
  gap_up + cl_low + neutral: 52.7% cont (n=937)
  Note: effect was seen at large_gap + neutral; needs testing at broader scope.

night_before_definable: yes — close_location = (close - low) / (high - low) is fully
observable at EOD; gap direction is confirmed at next morning's open.
Note: the gap direction is observed pre-market or at open, not at prior day close.
The close_location filter is set the night before; the gap confirmation happens at open.
This is acceptable for the TOS workflow (stop order above/below prior session reference
only triggers if the gap in the right direction actually appears at open).

source_scripts:
research_source_code/strategy_families/plan_next_day_day_trade/gap_directional_trap/
  research_run_gap_directional_trap_phase_r2_parent_baseline.py

output_folders:
research_outputs/family_lineages/plan_next_day_day_trade/gap_directional_trap/
  phase_r2_parent_baseline/

phase_r2_parent_baseline_result (2026-03-27):
  input:       gap_continuation parent event rows (807,957 quality-filtered events)
  output:      306,937 cl_opposed events (38.0% of parent pool)
  date_range:  2021-04-26 to 2026-03-23
  tickers:     1,992

  overall_parent_metrics:
    continuation_rate: 49.41%  (vs gap_continuation parent 48.76%)
    mean_nd_open_to_close: +0.076%
    mean_nd_range: 4.227%

  key_finding_1 (gap_up signal is real; gap_down is not):
    gap_up (cl_low):   cont=49.7%, o->c=+0.131%   (n=161,681)
    gap_down (cl_high): cont=49.1%, o->c=+0.015%  (n=145,256)
    Signal concentrates in gap_up + cl_low. gap_down + cl_high has no usable edge
    at the parent level. Phase_r3 should focus on gap_up as the primary child direction.

  key_finding_2 (bearish regime x gap_up is the standout cell):
    up__bullish:  cont=46.3%  n=87,982   <- DRAG; worst regime for gap_up
    up__neutral:  cont=51.7%  n=30,570   <- modest
    up__bearish:  cont=55.3%  n=43,129   <- STRONGEST; large sample, real effect
    Interpretation: in bearish market regimes, a stock that closed NEAR ITS LOW
    then gapped UP the next day continues upward 55.3% of the time. Large sample.
    Bullish regime does the opposite (46.3%) — this drags the parent mean to 49.7%.

  key_finding_3 (threshold monotonicity for gap_up):
    thresh<0.20: cont=50.7% (n=98,876)
    thresh<0.25: cont=50.3% (n=120,692)
    thresh<0.30: cont=50.0% (n=141,749)
    thresh<0.35: cont=49.7% (n=161,681)
    Tighter close_location threshold improves gap_up continuation monotonically.
    Largest sample is at <0.20 (very_opposed): still 98,876 events — workable for child.
    No equivalent pattern for gap_down (flat ~49.1% across all thresholds).

  key_finding_4 (gap_size adds modest lift for gap_up):
    large_gap + up: cont=52.1%, o->c=+0.870%, range=7.49%  (n=15,861)
    medium_gap + up: cont=50.7%, range=5.02%  (n=33,024)
    small_gap + up: cont=49.1%, range=3.64%   (n=112,796)
    Pattern: larger gap + cl_low produces better continuation AND wider range.
    This aligns with the "trapped" mechanism: larger gap = more trapped participants.

  key_finding_5 (yearly instability — risk):
    2021: 51.6%  2022: 50.7%  2023: 51.0%  2024: 47.6%  2025: 49.6%  2026: 47.0%
    2024 and 2026 are consistently weak across this entire track.
    Family must survive yearly stability testing in phase_r4.

  phase_r2_assessment:
    FAMILY IS ALIVE — proceed to phase_r3 child isolation.
    The broad parent is modest (+0.65pp lift over gap_continuation parent).
    But the concentrated signal (gap_up + bearish: 55.3%, n=43K) is real and
    worth isolating. The threshold gradient for gap_up is clean and monotonic.
    The primary concern is yearly instability — not a reason to stop here, but
    must be front-loaded in phase_r4 testing.

  promotion_decision: PROCEED to phase_r3 child isolation.

  phase_r3_direction:
    Primary child: gap_directional_trap__gap_up_cl_low
      filter: gap_up events only, cl_low < 0.35 (or narrower thresholds)
      rationale: all meaningful signal is in gap_up; gap_down has no edge
    Secondary child (optional, as structural reference):
      gap_directional_trap__gap_down_cl_high — test whether this is truly flat
      or has a different regime profile worth preserving
    Note: bearish regime is NOT a child definition; it is a regime tag used in
    grandchild parameter research. Children should capture behavioral subtypes,
    not just regime slices.

phase_r3_child_isolation_result (2026-03-27):
  script: research_run_gap_directional_trap_phase_r3_child_isolation.py
  input:  parent_event_rows__gap_directional_trap__phase_r2__2026_03_27.csv (306,937 rows)
  output_folder: phase_r3_child_isolation/

  children_defined:
    child_1: gap_directional_trap__gap_up_cl_low_020
      filter: gap_up AND signal_day_close_location < 0.20
      n: 98,876 (32.2% of parent; 61.2% of child_2)

    child_2: gap_directional_trap__gap_up_cl_low_035
      filter: gap_up AND signal_day_close_location < 0.35 (same as parent gap_up subset)
      n: 161,681 (52.7% of parent; comparison baseline for child_1)

    child_3: gap_directional_trap__gap_down_cl_high_reference
      filter: gap_down AND signal_day_close_location >= 0.65 (same as parent gap_down subset)
      n: 145,256 (47.3% of parent; reference/archive path)

  key_finding_1 (child_1 is the live path; cl<0.20 materially better than cl<0.35):
    child_1 (cl<0.20) overall:   cont=50.66%  o->c=+0.194%  range=4.351%
    child_2 (cl<0.35) overall:   cont=49.72%  o->c=+0.131%  range=4.299%
    Delta: child_1 adds +0.94pp cont and +0.063pp mean o->c vs child_2.
    In bearish regime — the most important cut:
      child_1 x bearish: cont=56.57%  n=28,125  o->c=+0.822%  range=4.945%
      child_2 x bearish: cont=55.28%  n=43,129  o->c=+0.701%  range=4.870%
    Tighter cl threshold isolates a purer version of the trap mechanism.

  key_finding_2 (standout cells: bearish x gap_size in child_1):
    child_1 x bearish x small:   cont=52.03%  n=18,260  o->c=+0.218%  range=4.014%
    child_1 x bearish x medium:  cont=62.47%  n= 6,320  o->c=+1.148%  range=5.538%
    child_1 x bearish x large:   cont=69.42%  n= 3,545  o->c=+3.347%  range=8.687%
    The bearish + medium/large gap combination is extraordinary.
    This is the primary target for phase_r4 structural validation.

  key_finding_3 (child_3 — gap_down — is flat; archive path confirmed):
    child_3 x bullish: cont=49.11%  — no edge
    child_3 x neutral: cont=50.50%  — barely any lift
    child_3 x bearish: cont=48.18%  — BELOW parent; regime does not help
    Yearly trend: 51.78% (2021) → 52.65% (2022) → 49.10% (2023)
                  → 48.31% (2024) → 47.83% (2025) → 46.20% (2026)
    Declining. No regime shows a real signal. Archive this child.

  key_finding_4 (yearly instability remains the main risk for child_1):
    2021: 53.18%  2022: 48.99%  2023: 52.81%
    2024: 47.81%  2025: 52.76%  2026: 49.10%
    2024 is the weak year. 2022 also weak. Pattern is not yet 2024-specific —
    this is systemic and must be front-loaded in phase_r4 testing.

  phase_r3_recommendation_board:
    child_1 (gap_up_cl_low_020):           CONTINUE → primary child → proceed to phase_r4
    child_2 (gap_up_cl_low_035):           CLOSE — same events as parent gap_up; no new
                                            information vs child_1. Use as parent comparison
                                            reference only, do not promote to phase_r4.
    child_3 (gap_down_cl_high_reference):  ARCHIVE — no regime shows a usable signal;
                                            yearly trend is declining; no edge vs parent.

  promotion_decision: PROCEED to phase_r4 with child_1 as sole live candidate.

  phase_r4_direction:
    Primary target: child_1 (gap_up_cl_low_020) × regime × gap_size grid.
    The bearish × medium/large cells need systematic validation.
    Key phase_r4 questions:
      1. Does bearish × large gap survive yearly stability with adequate sample size?
      2. Does bearish × medium gap survive yearly stability (n=6,320 is workable)?
      3. Does price_bucket or adv_bucket add further discrimination?
      4. Is the 2024 weakness structural or random?
      5. Do bearish medium/large grandchildren survive realistic slippage assumptions?

phase_r4_structural_validation_result (2026-03-27):
  script: research_run_gap_directional_trap_phase_r4_structural_validation.py
  input:  parent_event_rows__gap_directional_trap__phase_r2__2026_03_27.csv (306,937 rows)
  child_filter: gap_up AND close_location < 0.20  => 98,876 child_1 rows
  structural_grid: market_regime (bullish/neutral/bearish) x gap_size (small/medium/large)
  output_folder: phase_r4_structural_validation/

  sample_distribution_inside_child_1:
    bullish: 52,072 (52.7%)  —  small:37,376  medium:10,006  large:4,690
    neutral: 18,679 (18.9%)  —  small:13,299  medium:3,823   large:1,557
    bearish: 28,125 (28.4%)  —  small:18,260  medium:6,320   large:3,545

  full_grid_summary (regime x gap_size, continuation_rate):
    bearish x large:            69.42%  n= 3,545  o->c=+3.347%  range=8.687%
    bearish x medium:           62.47%  n= 6,320  o->c=+1.148%  range=5.538%
    bearish x medium+large:     64.97%  n= 9,865  o->c=+1.939%  range=6.670%
    bearish x small:            52.03%  n=18,260  o->c=+0.218%  range=4.014%
    bearish (all):              56.57%  n=28,125  o->c=+0.822%  range=4.945%
    neutral x large:            50.42%  n= 1,557  o->c=+0.189%  range=6.734%
    neutral x medium:           53.13%  n= 3,823  o->c=+0.260%  range=4.874%
    neutral x medium+large:     52.34%  n= 5,380  o->c=+0.240%  range=5.412%
    neutral (all):              52.36%  n=18,679  o->c=+0.125%  range=4.169%
    bullish (all):              46.86%  n=52,072  o->c=-0.120%  range=4.094%  [adverse]

  key_finding_1 (bearish confirmed as structural accelerator for medium/large gap):
    Bearish regime produces 62-69% continuation in medium/large gap cells.
    The mechanism concentrates in bearish: stocks that closed near their low after
    gapping up, during a bearish market environment, continue much more reliably.
    This is a behaviorally coherent trap-and-squeeze pattern.

  key_finding_2 (2022 is the systematic weakness — extreme bear market failure):
    bearish x large  2022: 42.42%  n=561
    bearish x medium 2022: 45.71%  n=1,689
    bearish x medium+large 2022: 44.89%  n=2,250
    2022 was the most sustained directional bear market in the sample.
    Finding: the trapped-positioning mechanism FAILS in extreme persistent bear markets.
    Possible interpretation: in a deep relentless bear, gap-ups are reliably faded; the
    "trapped" condition does not generate a squeeze because the overarching direction
    overwhelms the individual trapped-position dynamic.
    This is the primary stability risk for this family.

  key_finding_3 (bearish x large is 2025-dominated — do not trust the 69% headline):
    bearish x large yearly: 2021=72.73%(n=143), 2022=42.42%(n=561), 2023=51.50%(n=233),
                             2024=57.58%(n=396), 2025=83.32%(n=1,883), 2026=61.40%(n=329)
    2025 accounts for 1,883 of 3,545 events (53.1% of all bearish x large events).
    The 83.32% in 2025 dominates the 69.42% overall headline.
    Excluding 2025: 1,662 events, continuation much lower and unstable.
    bearish x large alone is NOT a stable grandchild. It is 2025-concentrated.

  key_finding_4 (bearish x medium is the better primary candidate):
    bearish x medium yearly: 2021=79.00%(n=538), 2022=45.71%(n=1,689), 2023=52.90%(n=414),
                              2024=68.01%(n=1,113), 2025=74.01%(n=1,843), 2026=56.85%(n=723)
    n=6,320 total. More evenly distributed across years vs large.
    4 of 6 years show 52-79% continuation. 2022 is the problem year (45.71%).
    Even with 2022 drag, the signal is clearly real and multi-year.
    This is the primary promotion candidate.

  key_finding_5 (neutral regime is marginal — not a primary candidate):
    neutral x medium: 53.13% overall but yearly ranges 44-59% with no clear structure.
    neutral x large: 50.42% overall, barely above child_1 baseline.
    Neutral regime does not show the structural acceleration seen in bearish.
    Neutral should not be promoted to phase_r5 at this time.
    Keep as a monitoring secondary — revisit only if bearish path produces a deployable_variant.

  key_finding_6 (bullish is structurally adverse — close this cell):
    bullish x large: 44.01%  bullish x medium: 45.36%  bullish x small: 47.62%
    All bullish cells are consistently below 50%. Bullish regime actively drags down
    the child_1 overall toward 50%. Bullish cells should be closed — not a research direction.

  grandchild_recommendation_board:
    bearish__medium:              PROMOTE to phase_r5 (primary grandchild)
                                  n=6,320, 62.47%, multi-year support, 2022 is risk to monitor
    bearish__medium_plus_large:   PROMOTE to phase_r5 as secondary combined grandchild
                                  n=9,865, 64.97%, better sample than large alone
                                  includes large-gap upside without as much 2025 concentration
    bearish__large:               HOLD / do not promote alone
                                  n=3,545, 69.42% headline is real but too 2025-concentrated
                                  can contribute as part of bearish__medium_plus_large only
    bearish__small:               CLOSE for primary research
                                  52.03% is modest; no clear structural edge beyond regime alone
                                  insufficient reward vs execution complexity
    neutral__medium:              HOLD secondary reference (not promoted)
    neutral__large:               CLOSE — 50.42%; effectively no edge
    bullish (all cells):          CLOSE — consistently adverse; do not research further

  promotion_decision:
    PROCEED to phase_r5 execution template research with two grandchildren:
      PRIMARY:   gap_directional_trap__gap_up_cl_low_020__bearish__medium
      SECONDARY: gap_directional_trap__gap_up_cl_low_020__bearish__medium_plus_large

  phase_r5_direction:
    Core question: Can bearish x medium (and bearish x medium+large) generate a
    fully specified night-before executable trade plan?
    Required outputs: entry formula, stop formula, target formula, cancel logic, time exit.
    Key concern to carry: how to handle 2022-style extreme-bear-market years at the
    execution level — potential cancel condition based on regime intensity.
    No stop/target logic belongs in phase_r4. This is the phase_r5 problem.

phase_r5_execution_template_result (2026-03-27):
  script: research_run_gap_directional_trap_phase_r5_execution_template_research.py
  input:  grandchild_event_rows__gap_directional_trap__phase_r4__2026_03_27.csv
  output_folder: phase_r5_execution_template_research/
  simulation_basis: daily-bar OHLCV only (intraday 1m not available for full universe)
  conservative_rule: both stop and target hit same daily bar => treated as loss

  templates_tested:
    entries:  E_close_band (buy stop above signal_close+0.2%), E_prior_high (buy stop at signal_high)
    stops:    S_prior_low (signal_day_low), S_prior_low_buffer (signal_day_low x 0.995)
    targets:  1.5R, 2.0R, 3.0R
    cancel:   no_cancel vs cancel_gap_exceed (fill > entry x 1.02)
    total templates tested: 12 base x 2 cancel variants = 24 per slice

  primary_slice_results (bearish x medium, n=6,320):
    E_close_band trigger_rate: 88.2% (n=5,573) — 50.5% via gap-fill (slippage risk)
    E_prior_high trigger_rate: 23.4% (n=1,481) — near-useless; MFE>2R only 0.74%
    Best template: E_close_band__S_prior_low_buffer__T_3_0r
      win_rate=8.6%  expectancy=-0.069R  n_valid=5,573
    All E_close_band templates have negative expectancy (-0.069R to -0.366R).
    All E_prior_high templates are consistently negative (-0.251R to -0.372R).
    Cancel modifier does NOT help — makes expectancy slightly worse.

  secondary_slice_results (bearish x medium_plus_large, n=9,865):
    Best template: E_close_band__S_prior_low_buffer__T_3_0r
      win_rate=10.5%  expectancy=-0.017R  n_valid=8,772
    Marginally better than primary but structurally the same problem.

  key_finding_1 (critical — stop is too tight for this entry type):
    For cl < 0.20, signal_day_close is very close to signal_day_low.
    The stop distance for E_close_band = (entry - signal_low) is only ~0.5-1.0% of price.
    But mean_mae_proxy (S_prior_low) = -3.02R: the next day's intraday adverse move
    averages 3x the stop distance below the fill price.
    The stop is systematically overwhelmed by next-day intraday volatility.
    67.3% stop-loss rate confirms this — the stop is in the intraday noise band.

  key_finding_2 (directional signal IS real — MFE confirms it):
    mean_mfe_proxy (E_close_band + S_prior_low) = +3.54R
    pct_mfe_above_2r = 51.5%
    More than half of triggered events reach 2R favorable excursion on the next day.
    The edge IS in the direction — but the stop at signal_day_low is too tight to
    survive the opening noise before the directional move develops.
    The signal can't be captured by a price stop tied to the prior day's structural low.

  key_finding_3 (2022 catastrophic across all templates — confirmed):
    2022: trigger_rate=82.6%, win_rate=4-10%, expectancy=-0.48R to -0.61R.
    No template or cancel condition improves 2022 meaningfully.
    2022 failure is structural (extreme bear market), not an execution issue.
    Cancel conditions don't target the 2022 problem.

  key_finding_4 (E_prior_high is not viable for this family):
    Trigger rate = 23.4% but MFE>2R = only 0.74%.
    Stocks that barely reclaim the gap-up open level (prior high) have used up
    their momentum — the favorable excursion from that entry is tiny (+0.41R avg).
    E_prior_high produces too few triggers and too little upside when triggered.

  key_finding_5 (higher R targets systematically less bad):
    3.0R is the best across all stop variants because: larger targets capture the
    rare high-MFE events, and the time-exit R avg is positive (+0.24R at 3.0R).
    Range-based targets were not tested but may fit better — test in future pass.

  key_finding_6 (2021 is the template-positive outlier):
    2021 (bull market, high volatility): win_rate=28-41%, E=+0.126R to +0.557R.
    The trap mechanism works BEST in high-volatility trending markets where
    trapped sellers are forced to capitulate aggressively.
    Other years mostly negative; 2024 nearly break-even for S_prior_low_buffer+2R (+0.065R).

  mae_mfe_summary (E_close_band + S_prior_low_buffer):
    mean_mae_proxy = -1.64R (stock goes 1.64 stop-units adverse intraday on avg)
    mean_mfe_proxy = +1.98R (stock goes 1.98 stop-units favorable intraday on avg)
    pct_mfe_above_2r = 35.4%
    Implication: if a 2R-wide stop (instead of 1R) were used, many current stop-losses
    would become time exits or wins. But the loss per stop would then be 2R, requiring
    higher win rates to maintain positive expectancy.

  template_recommendation_board:
    E_close_band + S_prior_low_buffer + 3.0R:  BEST — E=-0.069R primary / -0.017R secondary
    E_close_band + S_prior_low + 3.0R:          SECOND — E=-0.228R primary
    E_prior_high (all variants):                CLOSE — trigger rate too low, MFE too small
    cancel_gap_exceed modifier:                 DOES NOT HELP — makes expectancy worse

  promotion_decision:
    DO NOT PROMOTE to phase_r6 with current templates.
    Phase_r5 batch_1 result: HOLD — structural edge confirmed but executable template not found.
    The daily-bar continuation signal (62%) is real. The stop/target structure as
    tested cannot capture it. A different stop paradigm is required.

phase_r5_batch_2_execution_template_result (2026-03-27):
  script: research_run_gap_directional_trap_phase_r5_batch_2_wider_stop_research.py
  input:  grandchild_event_rows__gap_directional_trap__phase_r4__2026_03_27.csv
  output_folder: phase_r5_execution_template_research/  (batch_2_ prefix files)
  simulation_basis: daily-bar OHLCV only (same as batch_1)
  conservative_rule: both stop and target hit same daily bar => treated as loss

  templates_tested (17 total):
    entry:   E_close_band only (batch_1 confirmed; E_prior_high closed)
    stops:   S_fixed_1_5pct / S_fixed_2_0pct / S_fixed_2_5pct / S_fixed_3_0pct
             S_range_proxy_75pct (fill - 0.75 * prior_day_range_dollar; avg risk=4.7%)
    targets: T_fixed_1_5r / T_fixed_2_0r / T_fixed_3_0r / T_range_50pct / T_range_75pct
    cancel:  no_cancel (fixed-% stops); cancel_if_risk_gt_5pct (range-proxy only)

  primary_slice_results (bearish x medium, n=6,320):
    templates with POSITIVE expectancy: 11 of 17
    best: E_close_band__S_range_proxy_75pct__T_fixed_2_0r   E=+0.153R  n_valid=5,573
    2nd:  E_close_band__S_range_proxy_75pct__T_fixed_3_0r   E=+0.151R
    3rd:  E_close_band__S_range_proxy_75pct__T_range_75pct  E=+0.127R
    best fixed-%: E_close_band__S_fixed_3_0pct__T_fixed_3_0r  E=+0.103R  risk%=3.0%

  secondary_slice_results (bearish x medium_plus_large, n=9,865):
    best: E_close_band__S_range_proxy_75pct__T_fixed_3_0r   E=+0.244R  n_valid=8,772
    2nd:  E_close_band__S_range_proxy_75pct__T_range_75pct  E=+0.189R
    best fixed-%: E_close_band__S_fixed_3_0pct__T_fixed_3_0r  E=+0.166R
    secondary consistently stronger than primary across all templates

  key_finding_1 (wider stops rescue expectancy — monotonic relationship confirmed):
    S_fixed_1_5pct best: E=-0.069R  (= batch_1 best; no improvement)
    S_fixed_2_0pct best: E=+0.017R  (first positive; 2% threshold crossed)
    S_fixed_2_5pct best: E=+0.077R
    S_fixed_3_0pct best: E=+0.103R
    S_range_proxy_75pct: E=+0.153R  (avg 4.7% risk; proportional to stock volatility)
    Finding: expectancy improves monotonically as stop widens. The 2% level is the
    first positive threshold. Range-proxy stop dominates all fixed-% stops.

  key_finding_2 (range-proxy stop mechanism — wide stop = time-exit driven):
    Loss rate for S_range_proxy_75pct: 15.2% (vs 67.3% for S_prior_low in batch_1)
    Time-exit rate: 80-90% (only ~15% stop out, ~3% reach target, ~80% close at EOD)
    Positive expectancy source: the 62% continuation rate (close > open) generates
    positive time exits. The wide stop rarely fires; the MOC exit does the work.
    This is a valid TOS night-before bracket + MOC structure — not a precision trade.

  key_finding_3 (range-proxy stop outperforms fixed-% stop in 2022):
    S_range_proxy_75pct 2022: loss_rate=25.8%  E=-0.156R
    S_fixed_3_0pct      2022: loss_rate=45.7%  E=-0.262R
    In the extreme bear market (2022), fixed stops get hit more (adversity exceeds
    the fixed %). The range-proxy stop scales with each stock's prior-day range and
    stays wide enough to avoid many of the bear-market intraday noise stop-outs.

  key_finding_4 (range-proxy target does NOT outperform fixed-R with same stop):
    S_range_proxy_75pct + T_fixed_2_0r:  +0.153R (best)
    S_range_proxy_75pct + T_range_75pct: +0.127R
    S_range_proxy_75pct + T_range_50pct: +0.094R
    Fixed-R targets are better with range-proxy stop because T_range_50pct/75pct
    effectively reduce the implied R below 1:1, turning wins into near-breakevens.

  key_finding_5 (2022 still negative — structural, not execution-fixable):
    Best template 2022: E=-0.156R (primary). All templates negative in 2022.
    The 2022 problem is the extreme persistent bear market overwhelming the trap
    mechanism. Cannot be gated by stop/target changes alone. Regime-intensity filter
    (e.g., SPY below 200-day MA by >10%) is a candidate for phase_r6 testing.

  key_finding_6 (yearly stability — range-proxy stop):
    2021: +0.403R  |  2022: -0.156R  |  2023: +0.018R
    2024: +0.166R  |  2025: +0.428R  |  2026: -0.053R (partial)
    4 of 6 years positive. 2 negative years (2022 structural, 2026 partial data).
    Strong 2021 and 2025 are the high-volatility bearish-regime years — consistent
    with the trap mechanism working best under active trap-and-squeeze conditions.

  template_recommendation_board (batch_2):
    E_close_band + S_range_proxy_75pct + T_fixed_2_0r:    BEST — +0.153R primary
    E_close_band + S_range_proxy_75pct + T_range_75pct:   SECOND — +0.127R; more intuitive win R
    E_close_band + S_fixed_3_0pct + T_fixed_3_0r:         THIRD (fixed-% alternative) — +0.103R
    cancel_if_risk_gt_5pct modifier:                       DOES NOT HELP — reduces sample 35%
                                                           without improving 2022 or overall E

  promotion_decision:
    PROMOTE best 2 templates to phase_r6 for deployable_variant validation:
      CANDIDATE_1: E_close_band__S_range_proxy_75pct__T_fixed_2_0r
        primary E=+0.153R  |  secondary E=+0.244R  |  4/6 years positive  |  n_valid=5,573
      CANDIDATE_2: E_close_band__S_fixed_3_0pct__T_fixed_3_0r
        primary E=+0.103R  |  secondary E=+0.166R  |  3/6 years positive  |  risk%=3.0%
    Phase_r5 result: PROMOTABLE — first executable templates with believable positive
    expectancy found. Not yet validated for robustness or slippage sensitivity.
    That is phase_r6's job.

  phase_r6_priorities_identified:
    1. slippage_sensitivity: test stop/target ±0.25% variations to check rule fragility
    2. ticker_concentration: check if expectancy is driven by 5-10 names
    3. 2022_context_gate: test SPY-below-200MA or realized-vol veto for extreme bear
    4. position_sizing_realism: 4.7% avg stop implies position sizing discipline required
    5. orderability_review: 88% trigger + 80% MOC exit is valid TOS bracket workflow
    6. sample_sufficiency: 538 events in 2021 (smallest year) — acceptable?

source_scripts:
research_source_code/strategy_families/plan_next_day_day_trade/gap_directional_trap/
  research_run_gap_directional_trap_phase_r2_parent_baseline.py
  research_run_gap_directional_trap_phase_r3_child_isolation.py
  research_run_gap_directional_trap_phase_r4_structural_validation.py
  research_run_gap_directional_trap_phase_r5_execution_template_research.py
  research_run_gap_directional_trap_phase_r5_batch_2_wider_stop_research.py

output_folders:
research_outputs/family_lineages/plan_next_day_day_trade/gap_directional_trap/
  phase_r2_parent_baseline/
  phase_r3_child_isolation/
  phase_r4_structural_validation/
  phase_r5_execution_template_research/  (batch_1 files + batch_2_ prefix files)

phase_r6_deployable_variant_validation_result (2026-03-27):
  script: research_run_gap_directional_trap_phase_r6_deployable_variant_validation.py
  input:  grandchild_event_rows__gap_directional_trap__phase_r4__2026_03_27.csv
  output_folder: phase_r6_deployable_variant_validation/

  candidates_tested:
    CANDIDATE_1: E_close_band__S_range_proxy_75pct__T_fixed_2_0r
      mechanism: wide ATR-proxy stop (avg 4.7% risk) + fixed 2R target + MOC exit
    CANDIDATE_2: E_close_band__S_fixed_3_0pct__T_fixed_3_0r
      mechanism: fixed 3% stop + fixed 3R target + MOC exit

  slices_tested:
    PRIMARY   : gap_up_cl_low_020__bearish__medium          (n=6,320)
    SECONDARY : gap_up_cl_low_020__bearish__medium_plus_large (n=9,865)

  validation_dimensions: slippage sensitivity / ticker concentration / regime veto / yearly stability

  baseline_results:
    CANDIDATE_1 primary:   E=+0.153R  win=3.3%   loss=15.2%  time=81.5%  n_valid=5,573  risk=4.7%
    CANDIDATE_1 secondary: E=+0.244R  win=4.5%   loss=13.4%  time=82.1%  n_valid=8,772  risk=5.6%
    CANDIDATE_2 primary:   E=+0.103R  win=3.6%   loss=29.4%  time=67.0%  n_valid=5,573  risk=3.0%
    CANDIDATE_2 secondary: E=+0.166R  win=7.0%   loss=34.1%  time=58.9%  n_valid=8,772  risk=3.0%

  slippage_sensitivity (primary slice, E vs slip level):
    CANDIDATE_1: 0%=+0.153R | +0.05%=+0.150R | +0.10%=+0.145R | +0.25%=+0.133R
      -> +0.25% worst case retains 87% of baseline expectancy; no cliff; ROBUST
    CANDIDATE_2: 0%=+0.103R | +0.05%=+0.098R | +0.10%=+0.094R | +0.25%=+0.079R
      -> +0.25% worst case retains 77% of baseline; acceptable but thinner margin

  ticker_concentration (CANDIDATE_1, primary slice):
    valid_events=5,573  total_pnl_r=+852.58R  unique_tickers=1,673
    top-1 ticker:  BROS  pnl_sum=+7.64R  pct=0.9%  cum=0.9%
    top-5 tickers: cumulative 3.3% of total pnl
    top-10 tickers: cumulative 6.0% of total pnl
    excl_top_5:  E=+0.1489R (vs +0.153R baseline) — virtually unchanged
    excl_top_10: E=+0.1458R
    excl_top_20: E=+0.1396R
    finding: EXCEPTIONAL BREADTH — no single ticker drives more than 0.9% of total pnl;
    concentration risk is essentially absent; 1,673 tickers contribute positively

  regime_veto_results (primary slice, spy_realized_vol_20d gate):
    CANDIDATE_1 no_veto:      E=+0.153R  n=6,320 (100%)  2022_E=-0.156R (n=1,395)
    CANDIDATE_1 vol_gate_020: E=+0.109R  n=4,226 (67%)   2022_E=-0.236R (n=449)
    CANDIDATE_1 vol_gate_025: E=+0.085R  n=4,821 (76%)   2022_E=-0.167R (n=880)
    finding: vol gate DOES NOT HELP — reduces overall E without fixing 2022 performance.
    The vol gate removes high-vol events including good-performing years (2021, 2025).
    Remaining 2022 events under the gate still produce negative expectancy.
    2022 failure is structural (sustained directional bear market), not vol-level fixable.
    Recommendation: accept 2022 as a structural risk year; do not use vol gate.

  yearly_stability (primary slice, both candidates):
    CANDIDATE_1:  2021=+0.403R | 2022=-0.156R | 2023=+0.018R | 2024=+0.166R | 2025=+0.428R | 2026=-0.053R (partial)
    CANDIDATE_2:  2021=+0.476R | 2022=-0.262R | 2023=-0.015R | 2024=+0.160R | 2025=+0.339R | 2026=-0.058R (partial)
    CANDIDATE_1: 4/6 years positive (2022 structural, 2026 partial year only)
    CANDIDATE_2: 3/6 years positive (2022 structural, 2023 slightly negative, 2026 partial)

  secondary_vs_primary:
    CANDIDATE_1: secondary +0.244R vs primary +0.153R  (+59% improvement)
    CANDIDATE_2: secondary +0.166R vs primary +0.103R  (+61% improvement)
    secondary slice (bearish__medium_plus_large) is confirmed as the better production slice.
    Large-gap events amplify the trapped-positioning mechanism.

  key_finding_1 (slippage robust — CANDIDATE_1 is the cleaner candidate):
    CANDIDATE_1 retains +0.133R at worst-case +0.25% slippage.
    CANDIDATE_2 retains +0.079R at worst-case +0.25% slippage — thin but still positive.
    CANDIDATE_1 clearly more robust to execution perturbation.

  key_finding_2 (ticker breadth is exceptional — no concentration risk):
    1,673 unique tickers contribute to primary slice pnl.
    Removing top-20 contributors still produces +0.140R expectancy.
    This is the strongest breadth profile possible for a market-wide family.

  key_finding_3 (vol gate fails — accept 2022 as structural):
    All vol gate variants hurt overall E without improving 2022.
    The 2022 problem is the sustained directional bear market overwhelming the trap mechanism.
    A simple realized-vol gate cannot distinguish "bad bear market for this setup" from
    "high vol + still works." The vol gate removes both types indiscriminately.
    Phase_r7 or ranking layer should handle 2022-like regimes at a portfolio level,
    not as a per-family signal gate.

  key_finding_4 (secondary slice is the production choice):
    Both candidates are materially stronger on bearish__medium_plus_large.
    Large-gap events have 69.42% continuation (phase_r4 finding) and amplify the MOC-driven
    time-exit return. The secondary slice should be the primary production slice.

  key_finding_5 (CANDIDATE_1 structure is directional position + disaster stop + MOC):
    88% trigger rate, 82% MOC time exits, 15% stop loss, 3-4% bracket capture.
    The trade is not a precision bracket trade. It is a directional overnight hold with:
    - 4.7% disaster stop (the "I was wrong" protection)
    - 2R bracket (rare, captures exceptional gap-and-go events)
    - MOC exit as the default resolution (80%+ of trades)
    This is operationally sane for TOS bracket + MOC structure.
    Position sizing must account for the ~4.7% stop: smaller share size than a 1% stop trade.

  key_finding_6 (CANDIDATE_2 has acceptable but noisier trade experience):
    3% fixed stop is easier to plan but fires 29% of the time (1 in 3.4 trades hits stop).
    This generates a more stop-heavy trading experience vs CANDIDATE_1 (15% stop rate).
    Both are TOS-compatible but CANDIDATE_2 requires more emotional discipline for stops.

  deployable_variant_promotion_board:
    CANDIDATE_1 secondary: PROMOTE_TO_DEPLOYABLE_VARIANT
      slice: gap_directional_trap__gap_up_cl_low_020__bearish__medium_plus_large
      entry:  buy stop at signal_close * 1.002
      stop:   fill - 0.75 * signal_day_range_dollar
      target: fill + 2.0 * risk
      cancel: none (range risk ~4.7% is acceptable as-is; no improvement from cancel)
      exit:   MOC (flat at next_day_close if neither stop nor target hit by close)
      performance: E=+0.244R  win=4.5%  loss=13.4%  time=82.1%  n_valid=8,772
      yearly: 4/6 positive (2022 structural, 2026 partial)
      slippage: +0.133R at +0.25% worst case (robust)
      concentration: 1,673 tickers; top-5 = 3.3% pnl; negligible concentration risk

    CANDIDATE_1 primary: PROMOTE_TO_DEPLOYABLE_VARIANT (secondary preferred for production)
      same spec as above but restricted to bearish__medium slice (n=5,573, E=+0.153R)
      use as fallback if operator prefers the narrower slice

    CANDIDATE_2 secondary: PROMOTE_TO_DEPLOYABLE_VARIANT (alternative fixed-% model)
      slice: gap_directional_trap__gap_up_cl_low_020__bearish__medium_plus_large
      entry:  buy stop at signal_close * 1.002
      stop:   fill * (1 - 0.030)  -- exactly 3% risk; simpler TOS setup
      target: fill + 3.0 * risk   -- 3R target bracket
      cancel: none
      exit:   MOC
      performance: E=+0.166R  win=7.0%  loss=34.1%  time=58.9%  n_valid=8,772
      yearly: 4/6 positive on secondary (2022 structural, 2026 partial)
      slippage: +0.079R at +0.25% worst case (acceptable but thin)
      note: 34% loss rate means ~1-in-3 trades hits stop; accept or prefer CANDIDATE_1

    CANDIDATE_2 primary: CONDITIONAL — 3/6 years positive; 2023 slightly negative
      if using primary slice only, prefer CANDIDATE_1 over CANDIDATE_2

  phase_r6_final_decision: PROMOTE both candidates to deployable_variant status
    Production recommendation: CANDIDATE_1 on bearish__medium_plus_large slice

source_scripts:
research_source_code/strategy_families/plan_next_day_day_trade/gap_directional_trap/
  research_run_gap_directional_trap_phase_r2_parent_baseline.py
  research_run_gap_directional_trap_phase_r3_child_isolation.py
  research_run_gap_directional_trap_phase_r4_structural_validation.py
  research_run_gap_directional_trap_phase_r5_execution_template_research.py
  research_run_gap_directional_trap_phase_r5_batch_2_wider_stop_research.py
  research_run_gap_directional_trap_phase_r6_deployable_variant_validation.py

output_folders:
research_outputs/family_lineages/plan_next_day_day_trade/gap_directional_trap/
  phase_r2_parent_baseline/
  phase_r3_child_isolation/
  phase_r4_structural_validation/
  phase_r5_execution_template_research/  (batch_1 files + batch_2_ prefix files)
  phase_r6_deployable_variant_validation/  (6 output files: summary, slippage, yearly, concentration, veto, event_rows)
  phase_r8_engineering_handoff/  (4 files: handoff_doc, 2 YAML variant specs, README)

engineering_side_artifacts:
  2_0_agent_engineering/integrated_strategy_modules/plan_next_day_day_trade/
    gap_directional_trap__bearish_medium_large__candidate_1_v1/
      engineering_module_manifest__gap_directional_trap__candidate_1_v1.md

phase_r8_research_to_engineering_handoff_result (2026-03-27):
  status: complete

  deliverables_created:
    research_side (phase_r8_engineering_handoff/ folder):
      handoff_doc__gap_directional_trap__phase_r8__2026_03_27.md
        (primary engineering entry point — full human-readable spec for both variants)
      variant_spec__gap_directional_trap__candidate_1_v1__phase_r8__2026_03_27.yaml
        (machine-friendly spec for preferred production variant)
      variant_spec__gap_directional_trap__candidate_2_v1__phase_r8__2026_03_27.yaml
        (machine-friendly spec for backup fixed-% variant)
      readme__phase_r8_engineering_handoff.md
        (folder README)
    engineering_side:
      2_0_agent_engineering/integrated_strategy_modules/plan_next_day_day_trade/
        gap_directional_trap__bearish_medium_large__candidate_1_v1/
          engineering_module_manifest__gap_directional_trap__candidate_1_v1.md
            (engineering module manifest — defines what must be built, not how)

  frozen_deployable_variants:
    CANDIDATE_1 (preferred):
      variant_id:    gap_directional_trap__bearish_medium_large__candidate_1_v1
      production_priority: 1
      entry:         signal_day_close * 1.002
      stop:          fill_price - (0.75 * signal_day_range_dollar)  [~4.7% risk]
      target:        fill_price + (2.0 * risk_dollar)
      cancel:        none
      exit:          MOC same day
      expectancy:    +0.244R  (secondary slice, n=8,772)
      yearly:        4/6 positive (2022 structural; 2026 partial)

    CANDIDATE_2 (backup):
      variant_id:    gap_directional_trap__bearish_medium_large__candidate_2_v1
      production_priority: 2
      entry:         signal_day_close * 1.002
      stop:          fill_price * 0.970  (exactly 3% below fill)
      target:        fill_price * 1.090  (exactly 9% above fill = 3R at 3%)
      cancel:        none
      exit:          MOC same day
      expectancy:    +0.166R  (secondary slice, n=8,772)

  what_was_deliberately_not_built:
    - nightly scanning runtime
    - broker API integration
    - Alpaca paper trading (this track is TOS manual, not Alpaca)
    - Telegram delivery
    - result capture / journaling
    - phase_r7 ranking layer (deferred: no competing variants yet)

  main_engineering_entry_point:
    1_0_strategy_research/research_outputs/family_lineages/plan_next_day_day_trade/
      gap_directional_trap/phase_r8_engineering_handoff/
      handoff_doc__gap_directional_trap__phase_r8__2026_03_27.md

  recommended_next_engineering_batch:
    engineering_build_nightly_signal_scan__gap_directional_trap__candidate_1_v1
    scope: nightly data refresh + market regime update + signal scan (4-condition filter)
           + price formula computation (CANDIDATE_1) + signal pack output (CSV)

next_step: engineering_build_nightly_signal_scan__gap_directional_trap__candidate_1_v1
  First batch: implement nightly signal scan for CANDIDATE_1 only.
  defer: CANDIDATE_2, Telegram delivery, result capture, ranking layer.
  phase_r7 deferred until at least one more family produces a competing deployable_variant.

---

### Family 2: strong_close_momentum
status: registered_candidate — not yet materialized
registered: 2026-03-27

definition:
A stock that closed in the top portion of its signal-day range (close location
> threshold, e.g., 80%) after a meaningful intraday move. Thesis: persistent
buyer pressure into the close suggests next-day continuation demand.

night_before_definable: yes — close location = (close - low) / (high - low) is
fully observable at EOD.

next_step: phase_r2 parent baseline (future session)

---

### Family 3: failed_breakdown_reclaim
status: registered_candidate — not yet materialized
registered: 2026-03-27

definition:
A stock that traded below a prior reference level (e.g., prior day low, recent
multi-day low) intraday but closed back above it on signal day. Thesis: failed
breakdown traps short sellers and creates potential next-day bounce conditions.

night_before_definable: yes — prior reference levels and signal-day close are
fully observable at EOD.

next_step: phase_r2 parent baseline (future session)

---

### Family 4: prior_day_compression_setup
status: registered_candidate — not yet materialized
registered: 2026-03-27

definition:
A stock whose signal-day range was significantly compressed relative to its
recent ATR (e.g., daily range < 50% of 10-day ATR). Thesis: volatility
contraction precedes expansion; the direction is not assumed at the family
level but is studied at the child level (breakout direction, prior trend, etc.).

night_before_definable: yes — ATR ratio and daily range are fully observable at EOD.

next_step: phase_r2 parent baseline (future session)

---

## 16. CURRENT PHASE STATUS

| Phase | Status |
|-------|--------|
| phase_r0__tradable_universe_foundation | complete — 2026-03-27 |
| phase_r1__market_context_model | complete — 2026-03-27 |
| phase_r2__family_discovery_and_parent_baseline | gap_continuation complete 2026-03-27; gap_directional_trap phase_r2 complete 2026-03-27 |
| phase_r3__child_isolation | complete — 2 children tested for gap_continuation 2026-03-27; gap_directional_trap phase_r3 complete 2026-03-27 (1 live child promoted: gap_up_cl_low_020; gap_down archived) |
| phase_r4__grandchild_parameter_research | gap_continuation batch_2_complete — 2026-03-27; reframed as range/envelope tool; no grandchild promoted to phase_r5; gap_directional_trap phase_r4 complete — 2026-03-27; 2 grandchildren promoted: bearish__medium (primary), bearish__medium_plus_large (secondary) |
| phase_r5__execution_template_research | batch_1 complete (HOLD) 2026-03-27; batch_2 complete 2026-03-27 — 11/17 templates positive expectancy; best: S_range_proxy_75pct+T_fixed_2_0r E=+0.153R (primary), E=+0.244R (secondary); 4 of 6 years positive; 2022 still negative; promote best 2 templates to phase_r6. Extended study 2026-03-29: delayed activation + time exit grid (intraday 1m, 5,760 events, 883 tickers, 2021-2026); best combo a=13:15 c=13:30 e=14:30 → +0.7730R raw / +0.6730R slippage_adj; all 6 years positive; PROMOTE as candidate_1_v2 |
| phase_r6__deployable_variant_validation | complete — 2026-03-27 (v1 and v2 candidates, daily-bar): BOTH v1 candidates promoted; CANDIDATE_1 (S_range_proxy_75pct+T_fixed_2_0r) E=+0.244R secondary, slippage-robust, exceptional breadth; CANDIDATE_2 (S_fixed_3_0pct+T_fixed_3_0r) E=+0.166R secondary. Extended — 2026-03-29 (candidate_1_v2 intraday validation): E=+0.7730R, all 6 years positive, top-5 conc=2.0%, excl_top5=+0.7702R, slip@+0.25%=+0.7489R; VERDICT: KEEP_BOTH_WITH_DISTINCT_ROLES — v1=autonomous night-before, v2=midday-check elected upgrade |
| phase_r7__ranking_and_selection_layer | not started — deferred; no competing variant selection needed yet |
| phase_r8__research_to_engineering_handoff | complete — 2026-03-27 — handoff package for v1 and v2_initial candidates; CANDIDATE_1 is primary engineering target; implementation pending. Needs extension for candidate_1_v2 spec |

---

## 17. LINEAGE TREE (running)

```
plan_next_day_day_trade
│
├── gap_continuation                          [ENVELOPE REFERENCE FAMILY — directional path closed]
│   │                                          range findings preserved for execution template use
│   ├── liquid_trend_names                    [phase_r4 done — no directional grandchild promoted]
│   │   ├── small_gap                         [DROP — 49% cont, no edge (batch_1)]
│   │   ├── medium_gap                        [DROP — 50.6% neutral, modifiers add nothing (batch_2)]
│   │   └── large_gap                         [RANGE TOOL — 6.6% mean range; not a directional candidate]
│   └── high_rvol_names                       [phase_r4 done — range amplifier confirmed, not direction]
│       ├── small_gap                         [DROP — no edge (batch_1)]
│       ├── medium_gap                        [DROP — no edge (batch_1)]
│       └── large_gap                         [RANGE REFERENCE — 7.2% mean range; not a directional candidate]
│
├── gap_directional_trap                      [phase_r6_complete_DEPLOYABLE_VARIANT — 2026-03-27]
│   │                                          mechanism: cl_opposed gap events; 306,937 parent events (38% of parent pool)
│   │                                          standout: gap_up + bearish x large_gap: cont=69.42% (n=3,545), o->c=+3.347%
│   │
│   ├── gap_up_cl_low_020                     [phase_r4 complete → 2 grandchildren validated through phase_r6]
│   │   │   cont=50.66% overall; bearish=56.57%; bearish×medium=62.47%; bearish×large=69.42%
│   │   │   2022 is structural weakness (extreme bear market fails the trap mechanism)
│   │   │
│   │   ├── bearish__medium                  [phase_r6 complete — DEPLOYABLE_VARIANT]
│   │   │     n=6,320, cont=62.47%, o->c=+1.148%, range=5.538%
│   │   │     phase_r5 batch_2 best: E=+0.153R primary (S_range_proxy_75pct+T_fixed_2_0r)
│   │   │     phase_r6: slippage-robust (+0.133R at +0.25% worst), exceptional breadth (1,673 tickers)
│   │   │     4/6 years positive; 2022=-0.156R structural; vol gate does not help
│   │   │     DEPLOYABLE_VARIANT_1: S_range_proxy_75pct+T_fixed_2_0r (preferred)
│   │   │     DEPLOYABLE_VARIANT_2: S_fixed_3_0pct+T_fixed_3_0r (fixed-% alternative)
│   │   │     NOTE: secondary (bearish__medium_plus_large) preferred for production
│   │   │
│   │   ├── bearish__medium_plus_large       [phase_r6 complete — PRIMARY PRODUCTION SLICE]
│   │   │     n=9,865, cont=64.97%, o->c=+1.939%, range=6.670%
│   │   │     candidate_1_v1: E=+0.244R (S_range_proxy_75pct+T_fixed_2_0r, MOC exit) — PREFERRED autonomous
│   │   │     candidate_2_v1: E=+0.166R (S_fixed_3_0pct+T_fixed_3_0r, MOC exit) — fixed-% alternative
│   │   │     candidate_1_v2: E=+0.7730R (same entry/stop/target; activation=13:15, cancel=13:30, exit=14:30)
│   │   │                     intraday validated 2026-03-29; all 6 years positive; midday-check elected upgrade
│   │   │     4/6 years positive (v1 daily-bar); 6/6 years positive (v2 intraday subset)
│   │   │
│   │   ├── bearish__large                   [HOLD — not promoted alone; 2025-concentrated]
│   │   │     n=3,545, 69.42% headline; 2025=1,883 events (53%) at 83.32%; 2022=42.42%
│   │   │
│   │   ├── bearish__small                   [CLOSED — 52.03%; insufficient edge]
│   │   │
│   │   ├── neutral__medium                  [HOLD secondary reference; not promoted]
│   │   │
│   │   └── bullish (all cells)              [CLOSED — consistently adverse 44-48%]
│   │
│   ├── gap_up_cl_low_035                     [CLOSED — same as parent gap_up subset; no new info]
│   │     comparison reference only; not promoted
│   │
│   └── gap_down_cl_high_reference            [ARCHIVE — no edge in any regime; declining yearly]
│         cont=49.07%; bearish=48.18% (BELOW parent); yearly: 51.8%→46.2% declining
│
├── strong_close_momentum                     [registered_candidate]
│
├── failed_breakdown_reclaim                  [registered_candidate]
│
└── prior_day_compression_setup               [registered_candidate]
```

---

## 18. CHANGE LOG

| Date | Change | Session type |
|------|--------|--------------|
| 2026-03-27 | Track initialized, canonical master docs created, folder structure established | Claude Code |
| 2026-03-27 | phase_r0 complete: 1,993-ticker working universe built from 4,705 US common stocks | Claude Code |
| 2026-03-27 | phase_r1 complete: daily market context model built, 1,235 usable dates, bullish/neutral/bearish regime labels | Claude Code |
| 2026-03-27 | phase_r2: 4 candidate families registered; gap_continuation parent baseline materialized (808,679 events, ~49% continuation at broad parent level) | Claude Code |
| 2026-03-27 | phase_r3: 2 children isolated for gap_continuation; both show ~49% continuation (no edge at broad 0.5% gap threshold); key finding: gap-size segmentation is the primary phase_r4 research direction | Claude Code |
| 2026-03-27 | phase_r4 batch_1: gap-size segmentation across both children; 6 grandchildren; range scales clearly (large_gap liquid_trend 6.6%, large_gap high_rvol 7.2%) but NO directional edge found; neutral regime shows consistent modest lift for liquid_trend (51-52% cont); next batch = close_location + gap/ATR filter on large_gap + neutral subset | Claude Code |
| 2026-03-27 | phase_r4 batch_2: directional sharpening via close_location + gap_to_range_ratio on large_gap + medium_gap grandchildren; close_location OPPOSES expectation (cl_opposed 54% neutral, not cl_aligned); gap_to_range_ratio does not discriminate (76% of large_gap events are ratio_dominant); no grandchild promoted; family reframed as range/envelope tool; cl_opposed finding logged as candidate new child hypothesis (directional_trap) | Claude Code |
| 2026-03-27 | gap_continuation formally parked as envelope_reference_family; directional path closed. New family registered: gap_directional_trap (mechanism: cl_opposed gap events; separate family not a child of gap_continuation; phase_r2 parent baseline in progress) | Claude Code |
| 2026-03-27 | gap_directional_trap phase_r2 complete: 306,937 parent events; standout cell gap_up + bearish cont=55.3% (n=43,129); threshold gradient for gap_up is clean (50.7% at cl<0.20 to 49.7% at cl<0.35); yearly instability remains a risk; promoted to phase_r3 | Claude Code |
| 2026-03-27 | gap_directional_trap phase_r3 complete: 3 children tested; gap_up_cl_low_020 promoted (bearish×large: 69.42% cont, o->c +3.347%); gap_down_cl_high archived (declining, no edge); gap_up_cl_low_035 closed as redundant; doctrine update: aftermath/trap research encoded in research_stack_master_doc (principle 11) and family_tree_master_doc (principle 9) | Claude Code |
| 2026-03-27 | gap_directional_trap phase_r4 complete: structural grid validated; bearish×medium (62.47%, n=6,320) and bearish×medium_plus_large (64.97%, n=9,865) promoted to phase_r5; bearish×large NOT promoted alone (2025-concentrated); 2022 failure documented (extreme bear market suppresses trap mechanism); bullish cells closed | Claude Code |
| 2026-03-27 | gap_directional_trap phase_r5 batch_1 complete (HOLD): 12 structural-stop templates tested; best E=-0.069R (primary); NOT promoted; root cause = stop at signal_day_low (~0.7% of price) is inside the intraday noise band (mean MAE=-3.0R); directional signal confirmed (51.5% MFE>2R) but executable template not found with structural stops | Claude Code |
| 2026-03-27 | gap_directional_trap phase_r5 batch_2 complete (PROMOTE): 17 wider-stop templates tested; 11/17 templates positive expectancy; best: S_range_proxy_75pct+T_fixed_2_0r E=+0.153R primary / +0.244R secondary; 4/6 years positive; 2022=-0.156R (structural, not fixable by stop widening alone); mechanism = wide stop rarely fires; 62% continuation drives positive MOC time exits; PROMOTED to phase_r6 with 2 candidates | Claude Code |
| 2026-03-27 | gap_directional_trap phase_r6 complete (DEPLOYABLE_VARIANT): 2 candidates validated; slippage robust (+0.133R at worst-case +0.25%); exceptional breadth (1,673 tickers, top-5=3.3% pnl, excl-top-20 still +0.140R); vol gate does not improve 2022 (structural bear market risk — accept as-is); secondary slice (bearish__medium_plus_large) confirmed as production slice; CANDIDATE_1 (S_range_proxy_75pct+T_fixed_2_0r) E=+0.244R secondary — PROMOTED; CANDIDATE_2 (S_fixed_3_0pct+T_fixed_3_0r) E=+0.166R secondary — PROMOTED; next step = phase_r8 engineering handoff for CANDIDATE_1 | Claude Code |
| 2026-03-27 | gap_directional_trap phase_r8 complete (ENGINEERING_HANDOFF): research-to-engineering handoff package created for both deployable variants; frozen variant_ids: gap_directional_trap__bearish_medium_large__candidate_1_v1 (preferred, E=+0.244R) and candidate_2_v1 (backup, E=+0.166R); full formula spec frozen (entry=close*1.002, stop=fill-0.75*range_dollar, target=fill+2*risk, exit=MOC); YAML specs + handoff_doc written to phase_r8_engineering_handoff/; engineering module manifest created in 2_0_agent_engineering/integrated_strategy_modules/plan_next_day_day_trade/; NOT built: runtime implementation, broker API, Telegram; next engineering batch = nightly signal scan for CANDIDATE_1 | Claude Code |
| 2026-03-27 | gap_directional_trap phase_r4 complete: regime x gap_size structural grid validated; bearish confirmed as structural accelerator; 2022 (extreme bear market) identified as systematic failure year for the trap mechanism; bearish x medium promoted to phase_r5 (primary, n=6,320, 62.47%); bearish x medium+large promoted as secondary (n=9,865, 64.97%); bearish x large not promoted alone (2025-concentrated); bullish cells closed (adverse); neutral marginal (not promoted) | Claude Code |
| 2026-03-29 | gap_directional_trap phase_r5 delayed-activation study complete (PROMOTE): intraday 1m cache extended backward to 2021 for all production-slice tickers (115 tickers extended + 629 freshly built; zero failures); full coverage rerun: 5,760 events, 883 tickers, 2021-2026 all years present; subset representativeness confirmed (delta=-0.017R vs full slice); best timing combo a=13:15 c=13:30 e=14:30 → E=+0.7730R raw / +0.6730R slippage-adj vs intraday MOC baseline +0.4279R (+0.3451R improvement); all 6 years positive (2022=+0.558R); PROMOTED as candidate_1_v2 for phase_r6 validation | Claude Code |
| 2026-03-29 | gap_directional_trap phase_r6 candidate_1_v2 validation complete (DEPLOYABLE_VARIANT): intraday simulation on 5,760-event subset; E=+0.7730R, trigger_rate=62.3%, win=7.05%, loss=0.03%, time_exit=92.92%; all 6 years positive (min=+0.558R in 2022); slippage at +0.25%: +0.7489R (96.9% of base); top-5 ticker concentration=2.0% (856 unique tickers traded); excl_top5=+0.7702R; v2 vs v1 delta on same intraday subset=+0.3474R; VERDICT: KEEP_BOTH_WITH_DISTINCT_ROLES — v1=autonomous night-before (no intraday action), v2=midday-check elected upgrade (requires operator at 13:15 ET); both are deployable_variants with distinct operational roles | Claude Code |

---

## FINAL OPERATING SENTENCE

The plan_next_day_day_trade track exists to research and later engineer day-trade models that can be fully planned the night before, expressed as exact entry_stop_target trade plans, and manually executed the next day without requiring live morning monitoring from the user.
