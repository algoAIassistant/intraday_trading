# handoff_note__candidate_1_v2_as_live_variant__2026_03_29

date: 2026-03-29
document_type: operator_decision_note
scope: gap_directional_trap family — live variant selection

---

## Operator Decision

**candidate_1_v2 is the live production variant.**
**candidate_1_v1 is retained as research reference only. It is NOT an active engineering path.**

---

## What changed

The phase_r5 delayed activation study (2026-03-29) tested time-windowed entry variants
for the gap_directional_trap family. The winner was validated in phase_r6 v2 study (2026-03-29).

The result: a 13:15 ET activation window with 13:30 ET cancel-if-not-filled and
14:30 ET forced exit outperforms the v1 market-open activation with MOC exit on key quality metrics.

**v2 spec (frozen):**
- Signal logic: unchanged (gap_up, cl<0.20, bearish, medium/large gap)
- Entry: buy_stop at signal_day_close × 1.002
- Stop: fill_price − (0.75 × signal_day_range_dollar)
- Target: fill_price + (2.0 × risk_dollar)
- Activation: 13:15 ET (do not place at market open)
- Cancel if not filled: 13:30 ET
- Exit: forced flatten at 14:30 ET (not MOC)
- No broker auto-execution, no Alpaca

---

## What v1 reference means

- candidate_1_v1 engineering files remain in the repo under their original paths
- They serve as the validated research baseline and lineage record
- Do NOT run v1 nightly scans in production
- Do NOT maintain both v1 and v2 runtime output paths simultaneously
- The v2 orchestrator and GitHub Actions workflow are the sole production automation paths

---

## Research files confirming v2

| file | location |
|------|----------|
| v2_validation_summary | phase_r6_deployable_variant_validation/ |
| v2_yearly_breakdown | phase_r6_deployable_variant_validation/ |
| v2_slippage_sensitivity | phase_r6_deployable_variant_validation/ |
| v2_vs_v1_comparison | phase_r6_deployable_variant_validation/ |
| v2_concentration_check | phase_r6_deployable_variant_validation/ |
| delayed_activation_top_variants | phase_r5_execution_template_research/ |
| delayed_activation_yearly_breakdown | phase_r5_execution_template_research/ |

---

## Engineering handoff state for v2

| component | status |
|-----------|--------|
| variant_spec YAML | complete (this folder) |
| engineering module folder | complete (candidate_1_v2/) |
| nightly signal scan | complete |
| selection layer | complete |
| data refresh | complete |
| nightly orchestrator | complete |
| telegram delivery (polished) | complete |
| github_actions workflow | complete |
| secrets setup note | complete |
| operator summary | complete |

---

## Remaining manual steps (operator)

1. Add GitHub repo secrets: MASSIVE_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
2. Enable the GitHub Actions workflow in the Actions tab
3. Run a manual workflow_dispatch test to confirm the pipeline end-to-end
4. On each trade day: manually handle 13:15 ET order activation, 13:30 ET cancel, 14:30 ET exit in TOS
