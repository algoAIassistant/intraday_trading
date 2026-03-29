# engineering_module_manifest__gap_directional_trap__candidate_1_v2

document_type: engineering_module_manifest
track: plan_next_day_day_trade
family: gap_directional_trap
variant_id: gap_directional_trap__bearish_medium_large__candidate_1_v2
status: live_production_target
date: 2026-03-29

---

## Module identity

This is the live engineering module for the v2 variant.

**candidate_1_v2 is the only active nightly runtime path.**
**candidate_1_v1 is research reference only.**

Research handoff: `1_0_strategy_research/research_outputs/family_lineages/plan_next_day_day_trade/gap_directional_trap/phase_r8_engineering_handoff/`

---

## What this module does

Runs a nightly after-close pipeline that:

1. Fetches/extends the daily data cache (Stage 0)
2. Scans the universe for v2 signals (Stage 1)
3. Hard-filters and ranks the signal pack (Stage 2)
4. Delivers a clean Telegram message to the operator (Stage 3)

The output is a ready-to-use next-day day-trade plan for manual TOS execution.

---

## v2 execution identity (frozen)

| field | value |
|-------|-------|
| Signal logic | gap_up, cl<0.20, bearish regime, medium/large gap |
| Entry | buy_stop at signal_day_close × 1.002 |
| Stop | fill_price − (0.75 × signal_day_range_dollar) |
| Target | fill_price + (2.0 × risk_dollar) |
| Activation time | 13:15 ET (do NOT activate at market open) |
| Cancel if not filled | 13:30 ET |
| Forced exit | 14:30 ET (NOT MOC) |
| Broker auto-execution | None — fully manual TOS |
| Alpaca | Not used |

---

## Module file layout

```
gap_directional_trap__bearish_medium_large__candidate_1_v2/
├── __init__.py
├── engineering_module_manifest__gap_directional_trap__candidate_1_v2.md  (this file)
├── engineering_nightly_signal_scan__gap_directional_trap__candidate_1_v2.py
└── engineering_selection_layer__gap_directional_trap__candidate_1_v2.py
```

Companion files outside this folder:
- `2_0_agent_engineering/engineering_nightly_orchestrator__gap_directional_trap__candidate_1_v2.py`
- `2_0_agent_engineering/engineering_daily_data_refresh__gap_directional_trap__candidate_1_v2.py`
- `2_0_agent_engineering/engineering_source_code/notifications/telegram_delivery__gap_directional_trap__candidate_1_v2.py`
- `.github/workflows/nightly_gap_directional_trap_v2.yml`

---

## Signal filter (4 conditions — frozen)

| condition | rule |
|-----------|------|
| 1 | gap_direction == "gap_up" |
| 2 | signal_day_close_location < 0.20 |
| 3 | market_regime_label == "bearish" |
| 4 | gap_size_band in {medium, large} |

gap_size thresholds: small < 1.5%, medium 1.5–3.0%, large ≥ 3.0%

---

## Price formulas (frozen)

```
entry_price  = signal_day_close * 1.002
risk_dollar  = 0.75 * signal_day_range_dollar
stop_price   = entry_price - risk_dollar
target_price = entry_price + (2.0 * risk_dollar)
risk_pct     = risk_dollar / entry_price
```

---

## Selection layer hard filters (operator-facing)

| filter | threshold |
|--------|-----------|
| Stock type | US common stock (type == CS) |
| Price range | $20 – $100 |
| ADV_20 dollar volume | ≥ $2M / day |

Selection scoring weights: ADV 30%, close_location 30%, risk_pct 25%, RVOL 15%

Delivery: up to 3 signals (one bucket leader per occupied price bucket)

---

## Runtime outputs

```
2_0_agent_engineering/engineering_runtime_outputs/plan_next_day_day_trade/
  gap_directional_trap__candidate_1_v2/
    signal_pack__gap_directional_trap__candidate_1_v2__YYYY_MM_DD.csv
    ranked_signal_pack__gap_directional_trap__candidate_1_v2__YYYY_MM_DD.csv
    selected_top_3__gap_directional_trap__candidate_1_v2__YYYY_MM_DD.csv
    selection_summary__gap_directional_trap__candidate_1_v2__YYYY_MM_DD.md
```

---

## Data dependencies

| resource | path |
|----------|------|
| Shared universe | 0_1_shared_master_universe/shared_symbol_lists/shared_master_symbol_list_us_common_stocks.csv |
| Shared metadata | 0_1_shared_master_universe/shared_metadata/shared_master_metadata_us_common_stocks.csv |
| Daily OHLCV cache | 1_0_strategy_research/research_data_cache/daily/ |
| Market context model | 1_0_strategy_research/research_outputs/family_lineages/plan_next_day_day_trade/phase_r1_market_context_model/market_context_model_plan_next_day_day_trade.csv |

---

## Environment variables required

| variable | used by |
|----------|---------|
| MASSIVE_API_KEY | Stage 0 data refresh |
| TELEGRAM_BOT_TOKEN | Stage 3 Telegram delivery |
| TELEGRAM_CHAT_ID | Stage 3 Telegram delivery |

For GitHub Actions: set these as repository secrets.

---

## Research references

| phase | file |
|-------|------|
| r8 handoff | phase_r8_engineering_handoff/handoff_doc__gap_directional_trap__phase_r8__2026_03_27.md |
| r8 v2 spec | phase_r8_engineering_handoff/variant_spec__gap_directional_trap__candidate_1_v2__phase_r8__2026_03_29.yaml |
| r8 operator decision | phase_r8_engineering_handoff/handoff_note__candidate_1_v2_as_live_variant__2026_03_29.md |
| r6 v2 validation | phase_r6_deployable_variant_validation/v2_validation_summary__gap_directional_trap__phase_r6__2026_03_29.csv |
