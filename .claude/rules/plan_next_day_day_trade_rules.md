# Rules: plan_next_day_day_trade

Scope: any session where active track = plan_next_day_day_trade

---

## Canonical research stack reference

The full phase model and research logic for this track is defined in:

@../../0_0_work_protocols/project_master_documents/ai_trading_assistant__plan_next_day_day_trade__research_stack_master_doc.md

---

## Canonical living registry

The family tree, phase status, and lineage registry for this track is:
`0_0_work_protocols/project_master_documents/ai_trading_assistant__plan_next_day_day_trade__family_tree_master_doc.md`

Read this file at the start of any plan_next_day_day_trade session to check current phase status and family state.

Update this file when:
- a new family is registered after phase_r2 baseline
- a phase status changes
- a branch is closed or archived
- a deployable_variant is promoted to phase_r6

---

## Track identity — non-negotiable rules

- Track name is `plan_next_day_day_trade` — do not shorten to `plan_next_day` or any other abbreviation.
- This track belongs to `1_0_strategy_research` until a deployable_variant exits phase_r6.
- Execution model: `half_automation_half_manual_thinkorswim_conditional_orders`.
- This track is NOT the active Alpaca automation path. Alpaca automation belongs to `intraday_same_day`.
- Do not apply `intraday_same_day` defaults when this track is active.

---

## Research behavior rules

- All signal logic must use only information known at the close of the signal day.
- The user should not need to monitor the open. The plan must already be defined by the night before.
- Do not impose a single global reward:risk model. Each family earns its own execution template at phase_r5.
- Behavior discovery (phases r0–r4) and execution-template discovery (phase_r5) are permanently separated.
- The final research unit is a deployable_variant, not just a signal.
- Market context is a research tag at signal creation time — not a prediction about tomorrow.

---

## Phase sequence

```
r0: tradable_universe_foundation
r1: market_context_model
r2: family_discovery_and_parent_baseline
r3: child_isolation
r4: grandchild_parameter_research
r5: execution_template_research
r6: deployable_variant_validation
r7: ranking_and_selection_layer
r8: research_to_engineering_handoff
```

Do not skip phases. Engineering begins only after phase_r6 survival.

---

## Naming hierarchy for this track

```
track:              plan_next_day_day_trade
family:             gap_continuation
child:              gap_continuation__liquid_midprice_trend_names
grandchild:         gap_continuation__liquid_midprice_trend_names__price_10_20__adv_20m_plus__rvol_1_8_plus
deployable_variant: [grandchild_name]__[entry_style]__[stop_style]__[target_style]__[exit_style]
```

---

## Folder locations for this track

Source: `1_0_strategy_research/research_source_code/strategy_families/plan_next_day_day_trade/`
Output: `1_0_strategy_research/research_outputs/family_lineages/plan_next_day_day_trade/`
