# engineering_module_manifest__gap_directional_trap__candidate_1_v1

module_id:              gap_directional_trap__bearish_medium_large__candidate_1_v1
track:                  plan_next_day_day_trade
family:                 gap_directional_trap
production_priority:    1
research_status:        deployable_variant_phase_r6_validated_2026_03_27
engineering_status:     handoff_received — implementation pending
execution_model:        half_automation_half_manual_thinkorswim_conditional_orders
implementation_scope:   nightly_signal_scan_only (no broker API, no Alpaca, no live execution)

---

## Handoff source

Full research handoff doc:
  1_0_strategy_research/research_outputs/family_lineages/plan_next_day_day_trade/
    gap_directional_trap/phase_r8_engineering_handoff/
    handoff_doc__gap_directional_trap__phase_r8__2026_03_27.md

Machine-readable spec (YAML):
  1_0_strategy_research/research_outputs/family_lineages/plan_next_day_day_trade/
    gap_directional_trap/phase_r8_engineering_handoff/
    variant_spec__gap_directional_trap__candidate_1_v1__phase_r8__2026_03_27.yaml

Read those files before implementing anything in this folder.

---

## What this module will produce

A nightly signal scan that:
1. reads daily OHLCV data for all symbols in the shared master universe
2. applies the 4-condition signal filter (see spec)
3. computes entry_price, stop_price, target_price for each qualifying ticker
4. outputs a structured signal pack with required fields

The output of this module is a list of next-day trade plans — not live orders.
The operator manually places TOS bracket + MOC orders the night before.

---

## Signal filter (4 conditions — all must be true)

```
1. gap_direction == "gap_up"
   (next_day open expected > signal_day close)

2. signal_day_close_location < 0.20
   formula: (close - low) / (high - low) < 0.20

3. market_regime_label == "bearish"
   source: phase_r1 market context model (updated nightly)

4. gap_size_band in {"medium", "large"}
   medium: 0.015 <= abs(gap_pct) < 0.030
   large:  abs(gap_pct) >= 0.030
```

---

## Price formulas

```
entry_price  = signal_day_close * 1.002
stop_price   = entry_price - (0.75 * signal_day_range_dollar)
target_price = entry_price + (2.0 * (entry_price - stop_price))
risk_dollar  = entry_price - stop_price
risk_pct     = risk_dollar / entry_price  (≈ 4.7% average)
```

---

## Required output fields (nightly signal pack)

```
ticker
signal_date
next_trade_date
variant_id                  = "gap_directional_trap__bearish_medium_large__candidate_1_v1"
entry_price
stop_price
target_price
risk_dollar
risk_pct
cancel_condition_text       = "no mandatory cancel; order expires if not triggered"
same_day_exit_rule          = "MOC if neither stop nor target hit by session end"
gap_direction
gap_pct
gap_size_band
close_location_at_signal
market_regime_at_signal
signal_day_range_dollar
position_sizing_note
```

---

## Data dependencies

```
shared master universe:
  0_1_shared_master_universe/shared_symbol_lists/shared_master_symbol_list_us_common_stocks.csv

daily price cache (OHLCV):
  1_0_strategy_research/research_data_cache/daily/
  or engineering-maintained equivalent

market context model (updated nightly):
  1_0_strategy_research/research_outputs/family_lineages/plan_next_day_day_trade/
    phase_r1_market_context_model/market_context_model_plan_next_day_day_trade.csv
  required field: market_regime_label joined by date
```

---

## Implementation notes

1. do NOT implement broker API calls in this module
2. do NOT implement Alpaca paper trading (this track is TOS manual)
3. do NOT implement reactive intraday logic
4. the nightly scan is a batch job — run after market close, before midnight
5. the market context model must be updated as part of the nightly pipeline
   (SPY close today → regime label → joined into signal filter)
6. gap_pct at signal close is an estimate; the buy stop order handles
   the case where the stock opens below entry (order simply never triggers)
7. position sizing is the operator's responsibility; the module outputs
   risk_dollar and risk_pct to support sizing decisions
8. do NOT add CANDIDATE_2 to this module in the first implementation batch
   (add as a separate configuration in a later batch)

---

## Next engineering batch recommendation

```
batch_name: engineering_build_nightly_signal_scan__gap_directional_trap__candidate_1_v1

scope:
  - nightly data refresh step (daily OHLCV pull)
  - market regime update step (phase_r1 model refresh)
  - signal scan (4-condition filter)
  - price formula computation (entry/stop/target)
  - signal pack output (CSV or structured file)
  - basic scan logging

defer to later:
  - Telegram delivery
  - CANDIDATE_2 configuration
  - result capture / journaling
  - ranking layer
```

---

## Performance reference

```
expectancy:        +0.244R (secondary slice, 8,772 events, 2021-2026)
win_rate:          4.5%    (target hit intraday)
loss_rate:         13.4%   (stop hit intraday)
moc_exit_rate:     82.1%   (MOC is the primary resolution)
avg_risk:          ~4.7%   (range_proxy stop)
slippage_robust:   +0.133R at +0.25% worst case
breadth:           1,673 unique tickers; top-5 = 3.3% of total pnl
2022_risk:         structural (-0.156R primary); accept as regime risk
```
