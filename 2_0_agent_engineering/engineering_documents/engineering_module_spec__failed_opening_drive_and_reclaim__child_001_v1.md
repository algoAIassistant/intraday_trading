# Engineering Module Spec: failed_opening_drive_and_reclaim__child_001_v1

**Created:** 2026-03-26
**Track:** intraday_same_day
**Family:** failed_opening_drive_and_reclaim
**Frozen survivor:** child_001_v1
**Engineering phase:** phase_e0 (paper trading / replay only)

Research source:
`1_0_strategy_research/research_source_code/strategy_families/intraday_same_day/
failed_opening_drive_and_reclaim/frozen_survivors/
frozen_survivor__child_001_v1__failed_opening_drive_and_reclaim__2026_03_25.md`

---

## Frozen V1 rules (do not modify)

| Rule | Value |
|------|-------|
| Price filter | Session open $5.00–$20.00 |
| Drive direction | Down |
| Drive window | Bars 1–30 (09:30–09:59 ET, 1-minute bars) |
| Drive magnitude | Close of bar 30 must be >= 2.0% below session open |
| Reclaim trigger | Any post-drive bar (bar 31+) where close >= session open |
| Entry | Long at close of reclaim bar |
| Stop | None (destroys edge — do not add) |
| Target | None |
| Exit | 15:59 ET session close |
| Regime gate | Non-bearish month (universe-avg monthly OTC > -0.10%) |

Drive magnitude is measured as `(close_bar30 - session_open) / session_open * 100`.
This uses the close of bar 30 as the reference, not the intraday minimum low.
This matches the research reference implementation exactly.

---

## Module architecture

```
2_0_agent_engineering/
├── engineering_configs/
│   └── engineering_config__failed_opening_drive_and_reclaim__child_001_v1.yaml
├── engineering_documents/
│   └── engineering_module_spec__failed_opening_drive_and_reclaim__child_001_v1.md  ← this file
├── integrated_strategy_modules/
│   └── intraday_same_day/
│       └── failed_opening_drive_and_reclaim__child_001_v1/
│           └── engineering_strategy_module__failed_opening_drive_and_reclaim__child_001_v1.py
└── engineering_source_code/
    ├── market_climate_engine/
    │   └── engineering_market_climate_regime_gate.py
    ├── risk_engine/
    │   └── engineering_risk_portfolio_controls.py
    ├── broker_execution_adapters/
    │   └── engineering_broker_paper_fill_simulator.py
    ├── production_utilities/
    │   └── engineering_trade_logger.py
    └── signal_runners/
        └── engineering_signal_runner_intraday_same_day.py
```

---

## Layer responsibilities

### Layer 1: Strategy module (frozen detector)

File: `integrated_strategy_modules/intraday_same_day/
failed_opening_drive_and_reclaim__child_001_v1/
engineering_strategy_module__failed_opening_drive_and_reclaim__child_001_v1.py`

- Stateful per-ticker per-session detector
- Pure Python: no I/O, no logging, no external calls
- Consumes 1-minute bars one at a time via `on_bar()`
- Returns a `StrategySignal` when the reclaim trigger fires; silent otherwise
- Annotates `v4_early_reclaim` flag on every signal for future sizing use

```python
module = FailedOpeningDriveReclaimV1()
eligible = module.reset_session(ticker, session_open_price, session_date)
signal = module.on_bar(bar_time, bar_close)   # StrategySignal | None
```

### Layer 2: Market climate engine (regime gate)

File: `engineering_source_code/market_climate_engine/
engineering_market_climate_regime_gate.py`

- Determines whether a session date's calendar month is non-bearish
- In phase_e0: loads precomputed regime map CSV from research outputs
- Defaults to CLOSED (no trades) for any month not in the map

```python
gate = RegimeGate(mode="precomputed", regime_map_path="path/to/regime_map.csv")
is_ok = gate.is_non_bearish(session_date)
```

Regime map source (current):
`1_0_strategy_research/research_outputs/family_lineages/
failed_opening_drive_and_reclaim/child_001_price_filtered_regime_gated/
research_output_failed_opening_drive_and_reclaim__child001__regime_map__2026_03_25.csv`

Coverage: 2024-03 through 2025-12. For 2026+ dates, re-run the research
regime builder against updated cache data and update `regime_map_path` in the config.

### Layer 3: Risk engine (portfolio controls)

File: `engineering_source_code/risk_engine/
engineering_risk_portfolio_controls.py`

- Enforces max open positions, max position size, and daily loss limit halt
- Computes share count from portfolio value and max position size pct
- Does NOT add trade-level stops (see frozen research caution)

```python
risk = PortfolioRiskControls(portfolio_value_usd=50_000)
risk.begin_session(session_date, portfolio_value_usd)
decision = risk.evaluate_entry(ticker, entry_price, session_date)
risk.record_entry(ticker, fill_price, shares)
realized_pnl = risk.record_exit(ticker, exit_price)
```

### Layer 4: Broker adapter (paper fill simulator)

File: `engineering_source_code/broker_execution_adapters/
engineering_broker_paper_fill_simulator.py`

- Simulates fills at bar close price ± configurable slippage
- Roundtrip slippage split: half on entry (adverse), half on exit (adverse)
- Same fill model used in phase_r4 slippage analysis
- Interface matches the future Alpaca live adapter (swap without touching other layers)

```python
broker = PaperFillSimulator(roundtrip_slippage_bp=10)
entry_fill = broker.fill_entry(ticker, bar_time, bar_close, shares, ...)
exit_fill  = broker.fill_exit(ticker, bar_time, bar_close, shares, ...)
```

### Layer 5: Trade logger

File: `engineering_source_code/production_utilities/
engineering_trade_logger.py`

Per-session output files in `engineering_runtime_outputs/<strategy_id>/`:
- `signals__YYYY_MM_DD.csv` — ENTRY signals emitted
- `fills__YYYY_MM_DD.csv` — entry and exit fills
- `daily_summary__YYYY_MM_DD.json` — portfolio summary

### Layer 6: Signal runner (orchestrator)

File: `engineering_source_code/signal_runners/
engineering_signal_runner_intraday_same_day.py`

- Checks regime gate; skips session if bearish
- Initialises one `FailedOpeningDriveReclaimV1` instance per candidate ticker
- Feeds bars chronologically; routes signals through risk and broker
- Forces 15:59 ET exit for all open positions
- Returns session summary dict

---

## Data format contract

```
bar_data : Dict[str, pd.DataFrame]
    Keys   : ticker symbol
    Values : DataFrame
        Index   : pd.DatetimeIndex, tz-aware America/New_York
                  Index value = bar OPEN time (Polygon.io convention)
                  First bar of regular session: index = 09:30 ET
        Columns : open, high, low, close, volume
        Order   : ascending by time
```

Session open price = `df.between_time("09:30", "15:59").iloc[0]["open"]`

---

## Running a replay session

```python
import logging
import sys
import os
from datetime import date
from pathlib import Path

import pandas as pd

# Add engineering root to path
REPO_ROOT = "b:/git_hub/claude_code/ai_trading_assistant"
sys.path.insert(0, os.path.join(REPO_ROOT, "2_0_agent_engineering"))

from engineering_source_code.market_climate_engine.engineering_market_climate_regime_gate import RegimeGate
from engineering_source_code.risk_engine.engineering_risk_portfolio_controls import PortfolioRiskControls
from engineering_source_code.broker_execution_adapters.engineering_broker_paper_fill_simulator import PaperFillSimulator
from engineering_source_code.production_utilities.engineering_trade_logger import TradeLogger
from engineering_source_code.signal_runners.engineering_signal_runner_intraday_same_day import IntradaySameDaySignalRunner

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

REGIME_MAP = os.path.join(
    REPO_ROOT,
    "1_0_strategy_research/research_outputs/family_lineages/"
    "failed_opening_drive_and_reclaim/child_001_price_filtered_regime_gated/"
    "research_output_failed_opening_drive_and_reclaim__child001__regime_map__2026_03_25.csv"
)
OUTPUT_DIR = os.path.join(REPO_ROOT, "2_0_agent_engineering/engineering_runtime_outputs")
CACHE_DIR  = os.path.join(REPO_ROOT, "1_0_strategy_research/research_data_cache/intraday_1m")
STRATEGY_ID = "failed_opening_drive_and_reclaim__child_001_v1"
PORTFOLIO_VALUE = 50_000.0

gate    = RegimeGate(mode="precomputed", regime_map_path=REGIME_MAP)
risk    = PortfolioRiskControls(PORTFOLIO_VALUE, max_open_positions=5, max_position_size_pct=0.10)
broker  = PaperFillSimulator(roundtrip_slippage_bp=10)
tlogger = TradeLogger(output_dir=OUTPUT_DIR, strategy_id=STRATEGY_ID)
runner  = IntradaySameDaySignalRunner(gate, risk, broker, tlogger, PORTFOLIO_VALUE)

# Load tickers
tickers = ["SOUN", "IONQ", "MARA", "RIOT", "BITF"]
bar_data = {}
for ticker in tickers:
    p = Path(CACHE_DIR) / f"{ticker}.parquet"
    if p.exists():
        bar_data[ticker] = pd.read_parquet(p)

# Run one session
summary = runner.run_session(
    session_date=date(2025, 6, 16),
    candidate_tickers=list(bar_data.keys()),
    bar_data=bar_data,
)
print(summary)
```

---

## V4 overlay (future sizing)

V4 events (reclaim at bar <= 60) produce ~2.5× higher mean return per trade
(+1.219% vs +0.482%) with meaningfully better win rate (61.5% vs 53.0%).

Current status: annotated on every StrategySignal (`signal.v4_early_reclaim`).
Not used for sizing in V1. To activate:
- Add V4 sizing multiplier in `PortfolioRiskControls.evaluate_entry()` using
  the `v4_early_reclaim` flag from the signal metadata
- Configure multiplier in the YAML config under `v4_overlay.active_for_sizing`
- Do not change the strategy module or signal detection logic

---

## Regime map extension (2026+)

The current regime map covers 2024-03 through 2025-12. Running this module on
2026 dates will result in the regime gate returning CLOSED for all 2026 months
(safe default = no trades for unknown regime).

To extend:
1. Run the research regime builder script with updated cache data
2. Save the new regime map CSV (dated, e.g. `regime_map__2026_03_26.csv`)
3. Update `regime_map_path` in the YAML config

---

## Future ecosystem integration

This module is the first brick. The design supports future expansion:

- Add a second strategy family: create its module in `integrated_strategy_modules/`
  and instantiate it alongside V1 in the signal runner
- Swap to live broker: replace `PaperFillSimulator` with `AlpacaLiveAdapter`
  — no other changes needed
- Add V4 sizing: extend `PortfolioRiskControls` with a multiplier — no changes
  to strategy module or signal runner flow

---

*Spec current as of 2026-03-26. Update when engineering phase advances.*
