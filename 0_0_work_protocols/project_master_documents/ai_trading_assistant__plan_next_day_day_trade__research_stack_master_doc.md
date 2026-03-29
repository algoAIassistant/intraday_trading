# ai_trading_assistant__plan_next_day_day_trade__research_stack_master_doc

status: draft_v1
document_type: project_master_document
scope: research architecture for the plan_next_day_day_trade track

repo_alignment:
This document belongs to the existing ai_trading_assistant repo.
It defines the research stack for the track: plan_next_day_day_trade

recommended_repo_location:
0_0_work_protocols/project_master_documents/ai_trading_assistant__plan_next_day_day_trade__research_stack_master_doc.md

paired_master_document:
ai_trading_assistant__plan_next_day_day_trade__family_tree_master_doc

---

## 1. PURPOSE

This master document defines the research stack for: plan_next_day_day_trade

This track is for building next-day day-trade plans that are created after the close and manually placed in Thinkorswim using predefined prices.

The purpose of the research stack is:
- find behaviorally real setup families
- isolate stronger children and grandchildren
- test them across market context and universe cells
- attach night-before execution templates
- validate robustness
- promote only deployable_variants into engineering

The final research unit of this track is not just a signal.

The final research unit is: **deployable next-day bracket-ready trade plan**

---

## 2. TRACK DEFINITION

track_name: plan_next_day_day_trade

track_definition:
Research trading models that can generate, after the close of the signal day:
- entry price
- stop loss price
- take profit price
- cancel / no-trigger logic
- same-day exit rule

for manual next-day execution in Thinkorswim without requiring live morning monitoring from the user.

---

## 3. MASTER RESEARCH QUESTION

Using only information fully known at the close of day_t, can we identify high-quality next-day day-trade opportunities on day_t_plus_1 and express them as exact order-ready trade plans?

---

## 4. RESEARCH STACK OVERVIEW

The research stack for this track is:

- phase_r0: tradable_universe_foundation
- phase_r1: market_context_model
- phase_r2: family_discovery_and_parent_baseline
- phase_r3: child_isolation
- phase_r4: grandchild_parameter_research
- phase_r5: execution_template_research
- phase_r6: deployable_variant_validation
- phase_r7: ranking_and_selection_layer
- phase_r8: research_to_engineering_handoff

Only candidates that survive through phase_r6 should be considered serious deployment candidates.

---

## 5. PHASE_R0 — TRADABLE_UNIVERSE_FOUNDATION

phase_name: phase_r0__tradable_universe_foundation

purpose: define the stable tradable sandbox for this track

This phase is not strategy research yet.
This phase defines where strategy research is allowed to happen.

core outputs:
- eligible symbol universe
- stable price buckets
- liquidity buckets
- exclusion rules
- universe snapshots
- universe summary metrics

minimum research dimensions:
- U.S. common stocks only
- price bucket
- average share volume
- average dollar volume
- minimum liquidity rules
- optional ATR / daily range floor
- optional spread / tradeability proxy if available

example bucket dimensions:

price_buckets:
- price_2_5
- price_5_10
- price_10_20
- price_20_40
- price_40_80

average_dollar_volume_buckets:
- adv_2m_5m
- adv_5m_10m
- adv_10m_20m
- adv_20m_50m
- adv_50m_plus

average_share_volume_buckets:
- vol_250k_500k
- vol_500k_1m
- vol_1m_3m
- vol_3m_plus

research rule:
No child or grandchild should be trusted until the universe foundation is stable enough to avoid mixing untradeable junk with valid candidates.

promotion condition out of phase_r0:
A clean research universe and bucket structure exists and can be reused consistently across future phases.

---

## 6. PHASE_R1 — MARKET_CONTEXT_MODEL

phase_name: phase_r1__market_context_model

purpose: define the market context at the close of the signal day

important correction:
This phase does not try to predict tomorrow.
It only tags the market environment that exists when the signal is created.

role of the phase:
- provide context labels
- support regime slicing
- support research segmentation
- support future ranking logic
- support future message/reporting context

core outputs:
- market context labels by date
- context model rules
- context summary metrics
- stability checks for sample size and label balance

preferred first-version model:
- bullish
- neutral
- bearish

possible later expansion:
- bullish_light
- bullish_strong
- neutral_flat
- bearish_light
- bearish_medium
- bearish_heavy

possible input dimensions:
- SPY above or below moving averages
- QQQ above or below moving averages
- slope of short and medium moving averages
- realized volatility regime
- VIX regime
- later breadth if needed

research rule:
Keep the first version simple enough to preserve sample size.
Do not over-fragment the context model too early.

promotion condition out of phase_r1:
A stable market-context label exists for each signal day and can be joined into later research layers.

---

## 7. PHASE_R2 — FAMILY_DISCOVERY_AND_PARENT_BASELINE

phase_name: phase_r2__family_discovery_and_parent_baseline

purpose: identify broad setup families and create parent-level baseline studies

This phase answers: Which broad behavior types deserve deeper research?

examples of candidate families:
- gap_continuation
- failed_breakdown_reclaim
- failed_breakout_fade
- strong_close_next_day_momentum
- compression_breakout
- trend_pullback_reentry
- exhaustion_reversal_candidate

important note:
These are setup families, not final strategies.
They are broad archetypes used to organize research.

core outputs:
- family definitions
- parent baseline event sets
- baseline performance summaries
- context-sliced family summaries
- early rejection list for weak families

minimum parent-level questions:
- does the family show any real edge at all
- in which price buckets does it behave best
- in which liquidity buckets does it behave best
- under which market contexts does it improve or degrade
- can the family plausibly be translated into night-before execution

parent baseline output examples:
- event rowsets
- overall summary
- yearly summary
- market-context summary
- price-bucket summary
- liquidity-bucket summary

promotion condition out of phase_r2:
A family demonstrates enough structure or promise to justify child isolation.

---

## 8. PHASE_R3 — CHILD_ISOLATION

phase_name: phase_r3__child_isolation

purpose: split a promising family into meaningful behaviorally distinct subtypes

This phase answers: Which subtypes inside the family behave differently enough to deserve separate research treatment?

examples:

family: gap_continuation

possible children:
- gap_continuation__liquid_midprice_trend_names
- gap_continuation__high_rvol_small_midcaps
- gap_continuation__post_compression_names
- gap_continuation__trend_aligned_only

child split rules — create a new child when:
- the practical behavior is meaningfully different
- the best execution style changes
- the liquidity/speed profile changes enough to matter
- the context dependence changes enough to matter

do not create a child just because one threshold changes — that belongs in grandchild research.

core outputs:
- child definitions
- child-level event rowsets
- child-level summaries
- child comparison report inside the family
- rejected child list
- promoted child list

promotion condition out of phase_r3:
A child shows enough behavioral consistency and performance structure to justify parameter-cell research.

---

## 9. PHASE_R4 — GRANDCHILD_PARAMETER_RESEARCH

phase_name: phase_r4__grandchild_parameter_research

purpose: test filtered parameter cells inside a child

This phase answers: Which exact cells inside the child produce the cleanest and most usable behavior?

grandchild dimensions may include:
- price bucket
- average dollar volume bucket
- average share volume bucket
- relative volume threshold
- ATR threshold
- gap size bucket
- trend alignment rule
- market-context slice
- close location rule
- candle structure rule
- distance from moving averages
- prior-day range condition
- any stable non-random structural filter

examples:
- gap_continuation__liquid_midprice_trend_names__price_10_20__adv_20m_plus__rvol_1_8_plus
- gap_continuation__liquid_midprice_trend_names__price_20_40__adv_30m_plus__rvol_2_0_plus

important rule:
Grandchildren are not arbitrary combinations.
They must preserve the behavioral logic of the child.

core outputs:
- grandchild detail table
- grandchild comparison table
- sample-size diagnostics
- outlier sensitivity review
- market-context split review
- yearly stability review
- candidate promotion board

promotion condition out of phase_r4:
A grandchild demonstrates sufficiently strong and stable behavior to justify execution-template research.

---

## 10. PHASE_R5 — EXECUTION_TEMPLATE_RESEARCH

phase_name: phase_r5__execution_template_research

purpose: attach exact next-day execution logic to promising grandchildren

This is the defining phase of this track.
A candidate cannot become deployable until this phase exists.

This phase answers: Can the promising grandchild be turned into an exact night-before executable trade plan?

required components:
- entry formula
- stop formula
- target formula
- cancel / no-trigger rule
- same-day time-exit rule

possible entry styles:
- entry_above_signal_high
- entry_above_defined_trigger_band
- entry_on_pullback_to_predefined_level
- short_below_signal_low
- limit_entry_near_retest_level

possible stop styles:
- stop_below_signal_low
- stop_below_signal_low_minus_buffer
- stop_below_atr_band
- stop_below_structure_level

possible target styles:
- target_1r
- target_1_5r
- target_2r
- target_atr_expansion
- target_prior_resistance_band

possible cancel / no-trigger logic:
- cancel_if_not_triggered_by_time_x
- cancel_if_open_gaps_above_max_distance
- cancel_if_open_below_invalidation
- cancel_if_risk_distance_exceeds_threshold

possible same-day exit styles:
- flat_by_close
- flat_by_time_xx_xx
- time_exit_if_no_progress

important rule:
This phase must be fully compatible with the user's real-life workflow in Thinkorswim.
That means the result should be translatable into:
- exact price-based planning
- bracket logic
- conditional order logic where needed
- minimal user intervention

core outputs:
- execution-template comparison report
- entry/stop/target sensitivity study
- orderability review
- plan viability review
- promoted execution-ready candidates

promotion condition out of phase_r5:
A grandchild now has an exact night-before execution recipe and remains behaviorally acceptable after execution assumptions are applied.

---

## 11. PHASE_R6 — DEPLOYABLE_VARIANT_VALIDATION

phase_name: phase_r6__deployable_variant_validation

purpose: validate that an execution-ready candidate is strong enough to become a deployable_variant

This phase is the final research gate before engineering handoff.

required validation lenses:
- overall performance
- yearly stability
- market-context stability
- price-bucket consistency if relevant
- liquidity-bucket consistency if relevant
- sample-size sufficiency
- outlier dependence check
- slippage sensitivity
- rule fragility check
- risk/reward realism
- orderability realism

minimum questions:
- does the candidate still work after execution assumptions are applied
- is the result driven by only one abnormal period
- is the result too fragile to small threshold changes
- is the required stop too large for realistic use
- is the target too ambitious relative to next-day behavior
- is the setup too dependent on a rare market regime

required output identity fields:
- family_name
- child_name
- grandchild_name
- deployable_variant_name
- setup_definition
- universe_definition
- market_context_definition
- signal_definition
- entry_definition
- stop_definition
- target_definition
- time_exit_definition
- cancel_definition
- performance_summary
- risk_summary
- deployment_notes

promotion condition out of phase_r6:
The candidate becomes a deployable_variant and is eligible for ranking-layer integration and engineering handoff.

---

## 12. PHASE_R7 — RANKING_AND_SELECTION_LAYER

phase_name: phase_r7__ranking_and_selection_layer

purpose: decide how multiple deployable variants compete for selection on a given day

This phase answers: If several valid trade plans appear on the same signal day, which one or two should be delivered to the user?

ranking dimensions may include:
- expected return
- historical win rate
- context alignment score
- risk/reward quality
- slippage robustness
- liquidity quality
- sample-size confidence
- variant quality score
- conflict rules between similar candidates

possible outputs:
- rank_score
- confidence_band
- top_candidate
- top_2_candidates
- reject_if_below_threshold
- one_per_family rule if needed
- one_per_symbol rule
- one_per_context concentration rule

important: Ranking is not a substitute for research quality.
It sits on top of already validated deployable_variants.

promotion condition out of phase_r7:
A stable selection framework exists for deciding which validated plans should actually be sent to the user.

---

## 13. PHASE_R8 — RESEARCH_TO_ENGINEERING_HANDOFF

phase_name: phase_r8__research_to_engineering_handoff

purpose: translate validated research outputs into engineering-ready specifications

At this point the research unit is no longer abstract.
It is a fully specified deployable_variant.

research hands engineering:
- variant identity
- exact signal-day rules
- exact entry rule
- exact stop rule
- exact target rule
- exact cancel rule
- exact time exit rule
- market-context fields
- ranking fields
- required output fields for Telegram and reporting
- journaling fields
- deployment notes

expected engineering targets later:
- nightly scan runtime
- signal packaging
- ranking integration
- Telegram signal delivery
- journaling and result capture
- summary reports

not required at this stage:
- broker auto-execution
- live open monitoring
- streaming reaction engine

---

## 14. RESEARCH DATA LAYERS

data_layer_1: universe_reference_data
- symbol eligibility, market / exchange, share type, active status

data_layer_2: daily_price_and_volume_data
- ohlcv, atr, moving averages, daily range, close location, gap measures

data_layer_3: market_context_data
- SPY daily, QQQ daily, realized vol, context labels

data_layer_4: signal_event_rows
- candidate rowsets, parent / child / grandchild event sets

data_layer_5: execution_simulation_fields
- planned entry, planned stop, planned target, realized next-day path proxy, exit classification, time exit result

data_layer_6: ranking_and_deployment_fields
- rank score, confidence score, deployment eligibility, payload fields

---

## 15. REQUIRED RESEARCH OUTPUTS BY MATURITY LEVEL

maturity_level_1: family_candidate
- family definition, parent baseline, basic context summary

maturity_level_2: promoted_child
- child definition, child-level event study, comparison vs parent

maturity_level_3: promoted_grandchild
- parameter-cell definition, grandchild detail study, stability review

maturity_level_4: execution_ready_candidate
- entry/stop/target study, cancel logic, time exit logic, orderability review

maturity_level_5: deployable_variant
- full validation package, stable identity, ranking fields, engineering handoff package

---

## 16. RESEARCH PRINCIPLES

1. All signal logic must use only information known at the close of the signal day.
2. The user should not need to monitor the open.
3. Research must optimize for deployability, not just backtest attractiveness.
4. A strong family is not enough — it must survive child and grandchild isolation.
5. A strong grandchild is not enough — it must survive execution-template research.
6. A strong execution template is not enough — it must survive deployable variant validation.
7. Market context is a descriptive research tag, not a prediction claim.
8. Sample size and stability matter more than overly clever fragmentation.
9. A candidate that cannot generate exact entry_stop_target outputs the night before is not valid for this track.
10. Engineering should begin only after research produces deployable_variants.
11. Study the aftermath of obvious patterns. When a broad behavior is crowded or predictable, the researchable edge may concentrate in the failure, trap, reclaim, or reversal that follows it — not in the obvious headline setup itself.

---

## 17. RESEARCH FAILURE CONDITIONS

A candidate should be rejected or parked if:
- the sample is too small
- the edge disappears under realistic execution assumptions
- the result depends on one abnormal period
- the stop or target becomes unrealistic
- the setup cannot be translated into a night-before order plan
- the behavior changes too much across nearby thresholds
- the candidate only works in a regime too rare for practical use
- the user would need live discretionary interpretation to execute it

---

## 18. RECOMMENDED FIRST RESEARCH ORDER

First build:
- phase_r0 universe foundation
- phase_r1 market context model

Then start with one family only:
- one family
- a few children
- controlled grandchild research
- one or two execution templates
- one deployable variant attempt

recommended first-cycle scope:
- keep price buckets limited
- keep context model simple
- keep family count low
- keep execution template choices few
- prioritize clean structure over wide exploration

---

## 19. RELATIONSHIP TO FAMILY_TREE_MASTER_DOC

The family_tree_master_doc defines the structural hierarchy:
track -> family -> child -> grandchild -> deployable_variant

This research_stack_master_doc defines:
how research moves through that hierarchy in ordered phases

simple relationship:
family_tree_master_doc = structure
research_stack_master_doc = process

---

## 20. FINAL OPERATING SENTENCE

The research stack for plan_next_day_day_trade exists to move from broad next-day setup ideas to validated deployable_variants through a disciplined sequence of universe definition, market context tagging, family discovery, child isolation, grandchild parameter research, execution-template testing, robustness validation, and engineering handoff, all under the rule that the final output must be a night-before executable next-day trade plan for manual Thinkorswim use.
