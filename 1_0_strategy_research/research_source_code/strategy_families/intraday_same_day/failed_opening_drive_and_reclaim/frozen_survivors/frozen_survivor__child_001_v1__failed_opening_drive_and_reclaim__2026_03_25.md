# Frozen Survivor: child_001_v1 — failed_opening_drive_and_reclaim

**Freeze date:** 2026-03-25
**Status:** FROZEN — research complete, eligible for engineering handoff
**Track:** intraday_same_day
**Family:** failed_opening_drive_and_reclaim
**Branch:** child_001 (parent_002__child_001__price_filtered_regime_gated)
**Variant:** V1

---

## Complete locked rule specification

This is the authoritative rule set. Engineering must implement exactly this. No
modifications to these rules may be made without reopening research.

```
STRATEGY NAME   : failed_opening_drive_and_reclaim__child_001_v1
DIRECTION       : Long only
HOLDING PERIOD  : Intraday — same-day entry and exit, flat by close
MARKET CONTEXT  : U.S. common stocks, regular session hours (09:30–15:59 ET)
```

### Setup conditions (all must be true, evaluated at or before 10:00 ET)

```
1. REGIME FILTER
   Market month is non-bearish.
   Definition: universe-average open-to-close return (OTC) for the calendar
   month is > -0.10%.
   Computed from a universe of liquid U.S. common stocks (~200-300 names).
   Bearish months are excluded — no trades taken in bearish months.

2. PRICE FILTER
   Stock's session open price is in the $5.00–$20.00 range (inclusive).
   Price checked at session open (09:30 ET).

3. DRIVE CONDITION
   The stock makes a downward opening drive in the first 30 minutes (bars 1–30,
   i.e., 09:30–09:59 ET on a 1-minute bar basis).
   Drive direction: downward (drive_down).
   Drive magnitude: absolute decline from session open to drive-end low
   must be >= 2.0%.
   Drive end: the close of bar 30 (09:59 ET bar close).

4. RECLAIM CONDITION
   After the drive window ends (bar 30), the stock's 1-minute close price
   crosses back above the session open price (the level that was broken
   during the drive).
   Any bar from bar 31 onward may be the reclaim bar.
   There is no reclaim timing restriction in V1 — late reclaims count.
```

### Entry

```
ENTRY TRIGGER   : Close of the first bar where close >= session_open
                  (the reclaim bar), from bar 31 onward.
ENTRY PRICE     : Close of the reclaim bar.
ENTRY TIMING    : Executes at the close of the bar — end of that 1-minute bar.
DIRECTION       : Long.
```

### Stop, target, and exit

```
STOP            : None.
                  CRITICAL — do not add an intraday stop.
                  Research finding: structural stop at session_open hits 95%
                  of all events. Hard stop at -1.5% halves the t-stat.
                  The signal is a noisy mean-reversion — price routinely
                  re-crosses below session_open after initial reclaim before
                  ending the day positive. Any stop destroys the edge.

TARGET          : None.
                  Hold to close unless engineering risk controls require
                  an override (see implementation cautions below).

TIME EXIT       : 15:59 ET (session close).
                  Exit on the close of the 15:59 ET bar.
                  IMPORTANT: the last hour (15:00–15:59) contributes
                  meaningful alpha. Cutting to 15:00 exit is a viable
                  conservative fallback (t=2.08 at 15:00) but reduces
                  expected return by ~48% (from +0.482% to +0.249%).
                  Default is 15:59.
```

---

## Validated performance metrics

All figures are gross (no slippage, commission, or spread applied).
In-sample window: 2024-03-25 to 2025-12-31 (21 months, non-bearish only).
Regime exclusions: 2024-04, 2024-09, 2024-12, 2025-01, 2025-02, 2025-03, 2025-10.
Tickers: 166 processed (from 259-ticker liquid universe, price-filtered to $5-20).

### Phase_r4 locked metrics

| Split | N | Mean% | Win% | t-stat |
|-------|---|-------|------|--------|
| Full (21m) | 873 | +0.482% | 53.0% | +3.71 |
| IS 2024 | 323 | +0.214% | 50.8% | +0.98 |
| OOS 2025 | 550 | +0.640% | 54.4% | +3.96 |

OOS is stronger than IS. The 2025 (OOS) period independently confirms the
signal at t=3.96 without ever being used in hypothesis development.

### Slippage sensitivity

| Roundtrip slippage | Mean% | t-stat |
|--------------------|-------|--------|
| 0bp | +0.482% | +3.71 |
| 5bp | +0.432% | +3.33 |
| 10bp | +0.382% | +2.94 |
| 15bp | +0.332% | +2.56 |

Breakeven slippage: above 15bp roundtrip. At 10bp — realistic for $5-20 stocks
with limit orders — the edge holds strongly.

### Return distribution

```
p5  = -5.13%   p10 = -3.37%   median = +0.18%   p90 = +4.23%   p95 = +6.62%
std = 3.84%
```

### Concentration

- 128 tickers with events, 80 positive total return (62.5%)
- Top-5 tickers: 28.4% of positive return
- Top-10 tickers: 44.9% of positive return (threshold: 60%)
- 34 tickers needed to explain 80% of positive return

### Monthly stability

15 non-bearish months in the 21-month window.
Negative months: 5 of 15 (33%). No catastrophic inversion month.
Worst negative month mean: -0.37%. No bearish-month analog (all excluded by regime filter).

---

## Secondary variant: V4 (engineering-relevant overlay)

V4 is not the primary survivor. It is recorded here because it has potential
engineering relevance as a position sizing overlay or higher-conviction filter.

**V4 definition:** Same as V1 but restricted to early reclaims only (reclaim
occurs within bar 60, i.e., within 60 minutes of session open = within 30
minutes of drive end).

```
V4 Full  : n=166  mean=+1.219%  win=61.5%  t=+2.87
V4 OOS   : n=104  mean=+1.646%  win=63.5%  t=+3.13
V4 @ 15bp: mean=+1.069%  t=+2.51
```

Engineering interpretation: Early reclaim events (within 60 bars) produce
~2.5× higher mean return per trade with meaningfully better win rate.
If position sizing rules allow, V4-qualifying events may warrant larger
allocation. V4 does not replace V1 — it is a subset of V1 with a timing filter
that narrows the event set but improves per-trade quality.

---

## Key implementation cautions for engineering

These must be read before implementing this strategy in a production context.

### 1. No intraday stop — this is structural, not a gap

The absence of a stop is not a missing component. It is a validated structural
requirement. Any intraday stop eliminates the edge. Risk must be managed at the
portfolio level (position sizing, daily loss limits, regime gating) rather than
at the per-trade stop level.

If compliance or risk policy requires a hard stop, the most defensible fallback
is a hard stop at -8% to -10% (covering the p5 tail without cutting the noisy
mean-reversion). Even then, expect some degradation. Any stop below -5% will
likely eliminate much of the edge.

### 2. Regime filter is mandatory — not optional

The regime filter (non-bearish month gate) is not a performance enhancement. It
is a structural requirement. In bearish months, the signal inverts: mean
returns turn negative, win rates drop below 40%. The entire edge disappears in
bearish market conditions.

The regime filter must be computed and enforced before any trade is taken.
If the current calendar month cannot be regime-classified in real time,
the strategy should be gated off.

### 3. Price range $5–$20 is hard-coded

The signal is specific to this price tier. Stocks outside this range were
tested and show no meaningful edge. Higher-priced stocks ($20-100) showed near-
zero returns. The price check is at session open — if a stock opens outside
$5–$20, no trade regardless of drive magnitude.

### 4. Slippage reality in this price tier

Stocks priced $5–$20 carry real spread and slippage risk. At $5, a 1-cent
spread is 20bp roundtrip. Limit orders at the reclaim bar close are recommended
over market orders. If fills cannot be obtained within 2bp of the close price,
the strategy economics deteriorate materially at the lower end of the price range.

### 5. Single-name tail risk

The worst event in the 21-month research window was WOLF 2024-11-07 at -22.47%.
This was a news-driven gap event — not a reclaim failure. A single position
in a $5-20 stock on a high-news day can produce a severe drawdown even
when the setup signal was valid.

Position sizing must cap individual position exposure such that a -20%+ event
does not produce an unacceptable portfolio-level loss. Rule of thumb from the
tail distribution: plan for a p5 event (-5.1%) as a typical bad trade, and a
-15% to -25% event as a possible (low probability) tail.

### 6. WOLF-class outliers and news filters

Consider adding a pre-trade news filter or event calendar check (earnings,
FDA, merger announcements) to screen out high-news-day setups. This was not
tested in research and is not part of the locked rule set — but it is a
defensible engineering addition that would not alter the fundamental edge.

### 7. Exit execution at 15:59 ET

The 15:59 ET exit requires a market-on-close (MOC) order or a limit order
placed in the final minute of the session. If the broker does not support
MOC orders for these names, a 15:58 limit order is a practical fallback.
Do not let positions carry to the next day under any circumstances.

### 8. V4 early-reclaim events and position sizing

If V4 (early reclaim <=60 bars) is used as a sizing overlay, take care that
the additional allocation does not produce unacceptable concentration if
multiple V4 events occur on the same day in correlated names. Speculative
$5-20 stocks can be correlated in sector/momentum clusters.

---

## Research provenance summary

| Phase | Status | Key finding |
|-------|--------|-------------|
| phase_r0 | complete | Clean null baseline: drive_down unconditional mean = -0.104%, win = 47.5% |
| phase_r1 | complete | Large drive_down (>=2%) + reclaim: t=2.33 on 690 events |
| phase_r2 | complete | Signal regime-dependent and price-specific; child_001 required |
| phase_r3 | complete | 7 variants tested; V1 (no stop, hold to close) is winner at t=3.71 |
| phase_r4 | complete | All 7 robustness checks passed; OOS t=3.96; eligible for engineering |

Data source: Polygon.io intraday 1-minute bars, U.S. common stocks.
Cache window: 2024-03-25 to 2025-12-31 (21 months).
Tickers processed: 166 (of 259-ticker liquid universe, $5-20 price filtered).
Regime map: 295-ticker universe-average open-to-close return, monthly.

---

## Engineering handoff checklist

The following items must be addressed before this strategy enters live or
paper-trading production:

- [ ] Regime filter implementation: real-time monthly OTC calculation or
      pre-computed regime signal ingested from shared universe module
- [ ] Price filter: session open price check at 09:30 ET
- [ ] Drive detection: 1-minute bar monitoring from 09:30 to 09:59 ET
- [ ] Reclaim detection: 1-minute bar monitoring from 10:00 ET onward
- [ ] Entry execution: limit order at or near reclaim bar close
- [ ] Exit execution: MOC or 15:58 ET limit order
- [ ] Position sizing: defined before go-live (no sizing guidance from research)
- [ ] Portfolio-level risk controls: daily loss limit, max open positions
- [ ] News/event filter: optional but recommended (see caution 6 above)
- [ ] V4 overlay: optional; define separately if sizing overlay is used

---

## Document cross-references

| Document | Location |
|----------|----------|
| Family phase tracker | `research_source_code/strategy_families/intraday_same_day/failed_opening_drive_and_reclaim/family_master_phase_tracker.md` |
| Branch registry | `research_source_code/strategy_families/intraday_same_day/failed_opening_drive_and_reclaim/family_master_branch_registry.md` |
| Phase_r3 outputs | `research_outputs/family_lineages/failed_opening_drive_and_reclaim/phase_r3_strategy_formalization/` |
| Phase_r4 outputs | `research_outputs/family_lineages/failed_opening_drive_and_reclaim/phase_r4_robust_validation/` |
| Child_001 validation data | `research_outputs/family_lineages/failed_opening_drive_and_reclaim/child_001_price_filtered_regime_gated/` |

---

*This document is frozen as of 2026-03-25. Do not modify after freeze.*
*Any rule change or engineering deviation requires explicit research re-entry and re-validation.*
