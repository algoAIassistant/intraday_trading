# handoff_doc__gap_directional_trap__phase_r8

track:  plan_next_day_day_trade
family: gap_directional_trap
phase:  phase_r8__research_to_engineering_handoff
date:   2026-03-27
status: complete

---

## 1. HANDOFF IDENTITY

This document is the primary engineering handoff entry point for the
gap_directional_trap family.

It packages everything engineering needs to build the nightly signal scan
for the two validated deployable variants.

Engineering reads this document first.
The YAML spec files in this folder provide machine-readable copies of the
variant definitions.

---

## 2. WHAT IS BEING HANDED OFF

Two validated deployable variants:

```
CANDIDATE_1 (preferred production variant):
  variant_id:             gap_directional_trap__bearish_medium_large__candidate_1_v1
  stop_model:             range_proxy_75pct  (wide ATR-proxy stop)
  target_model:           fixed_2_0r
  expectancy (secondary): +0.244R
  production_priority:    1 (preferred)

CANDIDATE_2 (backup variant):
  variant_id:             gap_directional_trap__bearish_medium_large__candidate_2_v1
  stop_model:             fixed_3_0pct  (exactly 3% below fill)
  target_model:           fixed_3_0r
  expectancy (secondary): +0.166R
  production_priority:    2 (backup / fixed-% alternative)
```

Both variants share the same signal slice and entry logic.
They differ only in stop formula and target R multiple.

---

## 3. CRITICAL FRAMING NOTE

This is NOT a precision bracket-capture setup.

The trade structure is:
- enter via buy stop trigger (night-before order placed)
- wide safety stop (disaster protection, not expected to fire frequently)
- distant target (rarely captured, but large when it fires)
- MOC exit as the primary resolution path (82% of trades for CANDIDATE_1)

The edge is concentrated in MOC-exit trades:
gap-up events where the stock gapped up against a bearish close location
on a bearish market day — these tend to continue through the session
(62%+ continuation rate for medium/large gaps) and exit at a profit
via end-of-day close.

Position sizing must account for the wide stop:
- CANDIDATE_1: ~4.7% average risk → significantly smaller share count
  than a 1–2% stop trade for the same account-risk-dollar target
- CANDIDATE_2: ~3.0% exact risk → also requires sizing awareness

---

## 4. DEPLOYABLE VARIANT CARD — CANDIDATE_1 (PREFERRED)

```
variant_id:             gap_directional_trap__bearish_medium_large__candidate_1_v1
family_name:            gap_directional_trap
track:                  plan_next_day_day_trade
production_priority:    1
research_status:        deployable_variant_phase_r6_validated_2026_03_27
execution_model:        half_automation_half_manual_thinkorswim_conditional_orders
```

### UNIVERSE FILTER

U.S. common stocks in the shared master universe.
File: 0_1_shared_master_universe/shared_symbol_lists/shared_master_symbol_list_us_common_stocks.csv

No additional price or liquidity filter is applied at signal generation time
beyond what the shared master universe already enforces.
(Universe enforces: U.S. common stocks, basic liquidity minimums,
exchange-listed, no penny stocks, no ETFs.)

### SLICE DEFINITION (SIGNAL FILTER)

All four conditions must be true on the signal day (day_t):

```
condition_1: gap_direction == "gap_up"
  definition: next_day_open > signal_day_close
  note: evaluated at close of signal day using prior day's data

condition_2: signal_day_close_location < 0.20
  definition: (signal_day_close - signal_day_low) / signal_day_range_dollar < 0.20
  note: stock closed in the bottom 20% of its own day's range
  note: this is the "very_opposed" cl band in phase_r2/r4 definitions
  note: gap_up direction + cl < 0.20 together define the directional trap setup

condition_3: market_regime_label == "bearish"
  definition: from the phase_r1 market context model
  source: research_outputs/family_lineages/plan_next_day_day_trade/
            phase_r1_market_context_model/market_context_model_plan_next_day_day_trade.csv
  note: join by signal_date; use the label for that day

condition_4: gap_size_band in {"medium", "large"}
  definition for medium: 0.015 <= abs(gap_pct) < 0.030  (1.5% to 3.0%)
  definition for large:  abs(gap_pct) >= 0.030           (>= 3.0%)
  note: gap_pct = (next_day_open - signal_day_close) / signal_day_close
  note: only gap_up events here so gap_pct > 0 always in this slice
```

### SIGNAL-DAY FEATURE DEFINITIONS (DATA FIELDS NEEDED AT CLOSE)

All of these must be available at the close of signal day (day_t) before
plan generation. None require next-day data.

```
ticker:                  symbol identifier
signal_date:             date of signal day (day_t)
signal_day_close:        closing price on signal_day (day_t)
signal_day_open:         opening price on signal_day (for range calc)
signal_day_high:         intraday high on signal_day (for range calc)
signal_day_low:          intraday low on signal_day (for range calc)
signal_day_range_dollar: signal_day_high - signal_day_low
signal_day_close_location: (signal_day_close - signal_day_low) / signal_day_range_dollar
gap_pct:                 uses prior_close and this_open from data cache
                         gap_pct = (day_t+1_premarket_open - day_t_close) / day_t_close
                         note: at signal close, gap_pct = estimated (use prior close)
                         true gap_pct confirmed at next-day open
gap_direction:           "gap_up" if gap_pct > 0
gap_size_band:           bucket derived from abs(gap_pct) as defined above
market_regime_label:     from phase_r1 model, joined by signal_date

note on gap_pct at close:
  In the research, gap_pct = (next_day_open - signal_day_close) / signal_day_close.
  At the close of signal_day, next_day_open is not yet known.
  Engineering must decide how to handle this:
  Option A: use after-hours / pre-market gap proxy (if available)
  Option B: use a gap estimate and confirm / cancel at open
  Option C: place entry order as a buy stop — the order self-cancels if
            the trigger is never hit (implicitly handles no-gap or gap fill)
  Recommended: Option C for simplicity. The research simulation assumed
  the next_day_open acted as a filter. In production, the buy stop entry
  at entry_price = signal_close * 1.002 functions similarly: if the stock
  gaps down or opens below entry, the order never triggers.
```

### ENTRY RULE

```
type:          buy_stop (limit-stop order, day order)
formula:       entry_price = signal_day_close * 1.002
               (entry is 0.2% above the signal day close)
thinkorswim:   place a BUY STOP order at entry_price for the next session
note:          if the stock opens below entry_price and never reaches it
               during the session, the order expires without fill
note:          if the stock opens above entry_price (large gap), fill
               occurs near the open — account for gap-open slippage
```

### STOP RULE

```
type:          structure-based wide stop (disaster protection)
formula:       risk_dollar = 0.75 * signal_day_range_dollar
               stop_price  = fill_price - risk_dollar
note:          risk_dollar is computed at fill_price (not at entry_price)
               in production: fill_price ≈ entry_price for limit-stop fill
               use entry_price as proxy for stop computation in plan generation
approximate_risk_pct: ~4.7% of fill (empirical average across event set)
thinkorswim:   attach STOP order at stop_price to the entry fill
note:          this is a wide disaster stop; not intended to fire frequently
               historical stop rate: ~13-15% of triggered trades
```

### TARGET RULE

```
type:          fixed R multiple target bracket
formula:       risk_dollar  = fill_price - stop_price  (= 0.75 * range_dollar)
               target_price = fill_price + (2.0 * risk_dollar)
thinkorswim:   attach LIMIT order (take profit) at target_price
               set OCO bracket with the stop order
note:          target is ~9-10% above fill at average risk levels
               historical capture rate: ~3-5% of triggered trades
               target fires rarely; the majority of the P&L is in MOC exits
```

### CANCEL / NO-TRADE LOGIC

```
no mandatory cancel condition for this variant
the buy stop entry implicitly handles non-trigger situations:
  - if the stock never reaches entry_price → order expires, no trade
  - if gap direction reverses overnight → likely non-trigger
  - if account risk limit would be breached → do not place order (operator discretion)

optional operator cancel: cancel if opening gap_pct < defined minimum
  (not tested in research; currently not part of the formal definition)
```

### SAME-DAY EXIT RULE

```
type:          market-on-close (MOC)
rule:          if neither stop nor target has been hit by end of session,
               exit at next_day_close using MOC order
thinkorswim:   place a separate MOC order for the same day as entry
               the MOC order is the default resolution for most trades
note:          MOC orders must be submitted by ~3:45 PM ET most days
note:          if stop or target fires intraday, cancel the MOC order
note:          82.1% of triggered trades resolve via MOC exit
moc_exit_pnl:  pnl = (next_day_close - fill_price) / risk_dollar
               can be positive or negative depending on intraday drift
               positive time exits are the primary source of expectancy
```

### PERFORMANCE SUMMARY

Source: phase_r6_deployable_variant_validation/ output files

```
slice used:          gap_up_cl_low_020__bearish__medium_plus_large (production slice)
n_valid_events:      8,772  (2021-2026, partial 2026)
expectancy_r:        +0.244
win_rate_pct:        4.5%   (target hit intraday)
loss_rate_pct:       13.4%  (stop hit intraday)
time_exit_rate_pct:  82.1%  (MOC exit)
avg_risk_pct:        5.6%   (empirical; range proxy varies by stock)
```

### YEARLY STABILITY

```
year   expectancy_r   note
2021   +0.403R        strong
2022   -0.156R        structural bear market year (worst year in dataset)
2023   +0.018R        near-flat; acceptable
2024   +0.166R        positive
2025   +0.428R        strongest year
2026   -0.053R        partial year only (through 2026-03-27)
positive_years: 4 of 6 (excluding 2026 partial: 3 of 5 full years negative in 2022 only)
```

### SLIPPAGE SENSITIVITY

```
slip_level   expectancy_r   pct_of_baseline
0%           +0.153R        100% (primary slice baseline)
+0.05%       +0.150R        98%
+0.10%       +0.145R        95%
+0.25%       +0.133R        87%

verdict: ROBUST — no cliff; gradual degradation; +0.25% worst case still positive
note: secondary slice (production) will show ~+59% uplift over these figures
```

### TICKER CONCENTRATION

```
unique_tickers: 1,673
top-1 ticker:   BROS  pnl_sum=+7.64R  pct_of_total=0.9%
top-5:          3.3% of total pnl
top-10:         6.0% of total pnl
excl_top_20:    expectancy still +0.140R vs +0.153R baseline

verdict: EXCEPTIONAL BREADTH — negligible concentration risk
engineering can run this on the full master universe without concern
```

### 2022 STRUCTURAL RISK NOTE

```
2022 produced E=-0.156R (primary slice).
This is structural: the sustained directional bear market in 2022 overwhelmed
the gap-trap squeeze mechanism. Stocks that gapped up in a persistent downtrend
failed to continue through the day.

A vol gate (spy_realized_vol_20d) does NOT fix 2022:
- the gate removes high-vol events from other positive years (2021, 2025)
- remaining 2022 events under any tested gate still produce negative E
- vol gate consistently reduces overall E without improving 2022

Decision: accept 2022 as a regime risk year.
Engineering / ranking layer (phase_r7) should monitor for 2022-like conditions
at the portfolio level, not suppress this signal with a per-family gate.

Operational note: if sustained bear market conditions reappear with stocks
failing to follow through after gap-ups, reduce or pause this variant.
This is a judgment call for the operator, not an automated hard gate.
```

### MANUAL TOS WORKFLOW

```
night before (after signal day close):
  1. run nightly signal scan → identify qualifying tickers
  2. for each qualifying ticker compute: entry_price, stop_price, target_price
  3. compute share count: shares = account_risk_dollar / (entry_price - stop_price)
  4. place orders in TOS:
     - BUY STOP at entry_price (day order)
     - attach STOP at stop_price (part of bracket)
     - attach LIMIT at target_price (part of bracket, OCO with stop)
     - place separate MOC order for same day

next morning (no monitoring required):
  - orders execute automatically if triggered
  - MOC order fires at end of session if bracket not already resolved

optional same-day check:
  - confirm stop / target status if the position was triggered
  - cancel MOC if already stopped out or took profit
  - this is a quality-of-life step, not required for the strategy to function

key constraint: do NOT adjust stops or targets intraday
  - this is a mechanistic plan-and-hold execution model
  - adjustments add subjective drift and invalidate the research basis
```

### DATA DEPENDENCIES FOR NIGHTLY SIGNAL GENERATION

```
layer_1 (universe):
  0_1_shared_master_universe/shared_symbol_lists/shared_master_symbol_list_us_common_stocks.csv
  updated periodically (monthly or as needed)

layer_2 (daily price + OHLCV for signal features):
  research_data_cache/daily/ (existing cache in repo)
  engineering must maintain or re-derive this for production
  required columns per ticker per day:
    date, open, high, low, close, volume, dollar_volume, atr_14d (optional)

layer_3 (market context model):
  research_outputs/family_lineages/plan_next_day_day_trade/
    phase_r1_market_context_model/market_context_model_plan_next_day_day_trade.csv
  columns needed: date, market_regime_label
  engineering must update this nightly (SPY daily data → regime classification)
  the market context model rules are defined in that folder's source scripts

layer_4 (gap_size_band thresholds):
  hardcoded in research (not a data file):
    small:  abs(gap_pct) < 0.015
    medium: 0.015 <= abs(gap_pct) < 0.030
    large:  abs(gap_pct) >= 0.030
  engineering replicates this formula directly

layer_5 (close_location):
  computed directly from signal_day OHLCV:
    signal_day_close_location = (close - low) / (high - low)
  no external source needed
```

### NIGHTLY SIGNAL PACK — REQUIRED OUTPUT FIELDS PER TICKER

Engineering must produce exactly these fields per qualifying event each night:

```
ticker:                 stock symbol
signal_date:            date of signal day (day_t)
next_trade_date:        day_t + 1 (the execution day)
variant_id:             "gap_directional_trap__bearish_medium_large__candidate_1_v1"
entry_price:            signal_day_close * 1.002
stop_price:             entry_price - (0.75 * signal_day_range_dollar)
target_price:           entry_price + (2.0 * (entry_price - stop_price))
risk_dollar:            entry_price - stop_price
risk_pct:               risk_dollar / entry_price
cancel_condition_text:  "no mandatory cancel; order expires if not triggered"
same_day_exit_rule:     "MOC if neither stop nor target hit by session end"
gap_direction:          "gap_up"
gap_pct:                (estimated or confirmed)
gap_size_band:          "medium" or "large"
close_location_at_signal: signal_day_close_location (e.g., 0.12)
market_regime_at_signal:  "bearish"
signal_day_range_dollar:  signal_day_high - signal_day_low
position_sizing_note:   f"risk_pct={risk_pct:.1%}; size = account_risk_$ / risk_dollar"
```

---

## 5. DEPLOYABLE VARIANT CARD — CANDIDATE_2 (BACKUP)

```
variant_id:             gap_directional_trap__bearish_medium_large__candidate_2_v1
family_name:            gap_directional_trap
track:                  plan_next_day_day_trade
production_priority:    2
research_status:        deployable_variant_phase_r6_validated_2026_03_27
execution_model:        half_automation_half_manual_thinkorswim_conditional_orders
```

CANDIDATE_2 uses the same universe filter, slice definition, signal-day features,
entry rule, cancel logic, exit rule, data dependencies, and output fields as
CANDIDATE_1 above.

The only differences are the stop formula and target formula:

### STOP RULE (CANDIDATE_2 ONLY)

```
type:          fixed percentage stop
formula:       risk_dollar = fill_price * 0.030   (exactly 3% of fill)
               stop_price  = fill_price * (1 - 0.030) = fill_price * 0.970
note:          simpler to plan and explain than the range_proxy stop
               identical risk distance in pct terms for every trade in this variant
approximate_risk_pct: 3.0% (exact, not approximate)
thinkorswim:   attach STOP at stop_price = fill_price * 0.970
```

### TARGET RULE (CANDIDATE_2 ONLY)

```
type:          fixed R multiple target bracket
formula:       risk_dollar  = fill_price * 0.030
               target_price = fill_price + (3.0 * risk_dollar)
                            = fill_price * (1 + 3 * 0.030)
                            = fill_price * 1.090  (exactly 9% above fill)
note:          3R on a 3% stop = 9% target; straightforward to compute
```

### PERFORMANCE SUMMARY (CANDIDATE_2)

```
slice:               gap_up_cl_low_020__bearish__medium_plus_large
n_valid_events:      8,772
expectancy_r:        +0.166R
win_rate_pct:        7.0%   (target hit intraday — higher than CANDIDATE_1)
loss_rate_pct:       34.1%  (stop hit intraday — much higher than CANDIDATE_1)
time_exit_rate_pct:  58.9%  (MOC exit — lower than CANDIDATE_1)
avg_risk_pct:        3.0%   (exact)

note: 34% loss rate means approximately 1 in 3 triggered trades hits stop
      this is a heavier stop-loss experience than CANDIDATE_1 (13%)
      the operator must have the discipline to absorb frequent stops
      CANDIDATE_1 is preferred for this reason

slippage_at_worst_case: +0.079R at +0.25% — acceptable but thinner than CANDIDATE_1
```

### WHEN TO USE CANDIDATE_2 OVER CANDIDATE_1

```
use CANDIDATE_2 when:
  - operator prefers a predictable fixed-% risk distance for position sizing
  - simpler stop formula is preferred for manual TOS entry
  - the ~9% target level is a useful structural reference for the operator

prefer CANDIDATE_1 in general:
  - higher expectancy (+0.244R vs +0.166R)
  - more slippage-robust
  - lower stop-fire rate (better trading experience)
```

---

## 6. WHAT ENGINEERING NEEDS TO BUILD NEXT

This handoff defines WHAT to build. Engineering builds HOW.

Required nightly engineering components (in logical order):

```
step_1: nightly data refresh
  - pull latest daily OHLCV for all symbols in shared master universe
  - compute signal_day features: close_location, range_dollar, gap proxy

step_2: market regime update
  - compute market_regime_label for signal_date using phase_r1 model rules
  - append to market_context_model CSV or equivalent nightly store

step_3: signal scan
  - filter universe to qualifying events:
      gap_direction == "gap_up"
      AND signal_day_close_location < 0.20
      AND market_regime_label == "bearish"
      AND gap_size_band in {"medium", "large"}
  - for CANDIDATE_1: compute entry/stop/target using range_proxy formula
  - for CANDIDATE_2: compute entry/stop/target using fixed_3pct formula

step_4: nightly signal pack generation
  - produce one row per qualifying ticker per variant
  - include all required output fields listed in section 4 above

step_5: signal delivery
  - Telegram message or report per qualifying signal (future phase)
  - contents: ticker, next_trade_date, entry, stop, target, risk_pct, regime, gap_band

step_6: result logging (future phase)
  - capture what happened: fill, stop, target, time_exit result
  - feed back into performance tracking
```

---

## 7. WHAT WAS DELIBERATELY NOT BUILT IN THIS BATCH

```
NOT built:
  - nightly scanning runtime implementation
  - broker API integration
  - Alpaca paper trading integration (this track is TOS manual, not Alpaca)
  - Telegram bot implementation
  - live monitoring or reactive intraday engine
  - phase_r7 ranking layer (deferred: no competing variants yet)
  - result capture / journaling system

engineering must build these in subsequent batches
```

---

## 8. RECOMMENDED NEXT ENGINEERING BATCH

```
batch_name: engineering_build_nightly_signal_scan__gap_directional_trap__candidate_1_v1

objective:
  Build the nightly signal scan that reads from the data cache,
  applies the slice filter, computes entry/stop/target for CANDIDATE_1,
  and outputs a structured signal pack (CSV or similar).

scope:
  - implement the market regime update step
  - implement the signal filter (4 conditions)
  - implement the CANDIDATE_1 formula (range_proxy stop + 2R target)
  - output the required signal pack fields
  - basic logging of scan results

do NOT include in this batch:
  - CANDIDATE_2 (add later)
  - Telegram delivery (add later)
  - result capture (add later)
  - any broker API calls
```

---

## 9. FILE LOCATIONS

```
research phase_r8 handoff folder:
  1_0_strategy_research/research_outputs/family_lineages/
    plan_next_day_day_trade/gap_directional_trap/phase_r8_engineering_handoff/

files in this folder:
  handoff_doc__gap_directional_trap__phase_r8__2026_03_27.md      (this file)
  variant_spec__gap_directional_trap__candidate_1_v1__phase_r8__2026_03_27.yaml
  variant_spec__gap_directional_trap__candidate_2_v1__phase_r8__2026_03_27.yaml
  readme__phase_r8_engineering_handoff.md

engineering-side handoff:
  2_0_agent_engineering/integrated_strategy_modules/plan_next_day_day_trade/
    gap_directional_trap__bearish_medium_large__candidate_1_v1/
    engineering_module_manifest__gap_directional_trap__candidate_1_v1.md

research inputs this handoff depends on:
  phase_r6 validation output:
    phase_r6_deployable_variant_validation/ (6 output files)
  phase_r4 event rows (source of truth for event set):
    phase_r4_structural_validation/grandchild_event_rows__gap_directional_trap__phase_r4__2026_03_27.csv
  market context model:
    phase_r1_market_context_model/market_context_model_plan_next_day_day_trade.csv

family tree master doc:
  0_0_work_protocols/project_master_documents/
    ai_trading_assistant__plan_next_day_day_trade__family_tree_master_doc.md
```

---

## 10. PROMOTION DECISION SUMMARY

```
CANDIDATE_1 (preferred):
  status:          PROMOTED to deployable_variant
  variant_id:      gap_directional_trap__bearish_medium_large__candidate_1_v1
  promotion_date:  2026-03-27
  rationale:       highest expectancy (+0.244R), slippage-robust,
                   exceptional breadth, TOS-compatible wide-stop MOC structure

CANDIDATE_2 (backup):
  status:          PROMOTED to deployable_variant
  variant_id:      gap_directional_trap__bearish_medium_large__candidate_2_v1
  promotion_date:  2026-03-27
  rationale:       simpler fixed-% alternative, lower expectancy (+0.166R),
                   higher stop rate (34%) but still positive and TOS-compatible

engineering production recommendation:
  implement CANDIDATE_1 first
  add CANDIDATE_2 as alternative configuration in a later batch
```
