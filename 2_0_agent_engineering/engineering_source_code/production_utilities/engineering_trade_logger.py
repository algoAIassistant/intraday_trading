"""
engineering_trade_logger.py

Structured logging for signals, fills, and daily summaries.

Creates per-session output files in the configured output directory:
    signals__YYYY_MM_DD.csv         — all ENTRY signals emitted by strategy modules
    fills__YYYY_MM_DD.csv           — all paper fills (entries and exits)
    daily_summary__YYYY_MM_DD.json  — end-of-day portfolio summary

Files are written to:
    2_0_agent_engineering/engineering_runtime_outputs/<strategy_id>/

Interface:
    logger = TradeLogger(output_dir="...", strategy_id="...")
    logger.begin_session(session_date)
    logger.log_signal(signal)       # StrategySignal
    logger.log_fill(fill)           # Fill
    logger.log_daily_summary(dict)
    logger.end_session()

Output files are not committed to git (engineering_runtime_outputs/ is gitignored
or excluded via project convention). They exist for inspection and analysis only.
"""

from __future__ import annotations

import csv
import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Column definitions — kept stable so downstream analysis scripts stay valid
_SIGNAL_FIELDS = [
    "session_date", "strategy_id", "ticker", "signal_type", "direction",
    "bar_time", "bar_index", "trigger_price", "session_open_price",
    "drive_magnitude_pct", "v4_early_reclaim",
]

_FILL_FIELDS = [
    "session_date", "strategy_id", "ticker", "fill_type", "direction",
    "fill_time", "fill_price", "fill_price_raw", "shares",
    "slippage_bp", "simulated",
]


class TradeLogger:
    """
    Per-session trade logger. Writes structured CSV and JSON output files.

    One instance per strategy module per signal runner. Safe to reuse across
    multiple sessions by calling begin_session() / end_session() for each day.
    """

    def __init__(self, output_dir: str, strategy_id: str) -> None:
        """
        Parameters:
            output_dir  : root output directory; files go in <output_dir>/<strategy_id>/
            strategy_id : used to namespace output files per strategy
        """
        self.strategy_id = strategy_id
        self._session_dir = Path(output_dir) / strategy_id
        self._session_dir.mkdir(parents=True, exist_ok=True)

        self._session_date: Optional[date] = None
        self._signal_fh = None
        self._fill_fh = None
        self._signal_writer: Optional[csv.DictWriter] = None
        self._fill_writer: Optional[csv.DictWriter] = None
        self._signal_count: int = 0
        self._fill_count: int = 0

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def begin_session(self, session_date: date) -> None:
        """Open output files for the session. Call at session start."""
        if self._session_fh_open():
            self.end_session()

        self._session_date = session_date
        date_str = session_date.strftime("%Y_%m_%d")

        signal_path = self._session_dir / f"signals__{date_str}.csv"
        fill_path = self._session_dir / f"fills__{date_str}.csv"

        self._signal_fh = open(signal_path, "w", newline="", encoding="utf-8")
        self._fill_fh = open(fill_path, "w", newline="", encoding="utf-8")

        self._signal_writer = csv.DictWriter(self._signal_fh, fieldnames=_SIGNAL_FIELDS)
        self._fill_writer = csv.DictWriter(self._fill_fh, fieldnames=_FILL_FIELDS)
        self._signal_writer.writeheader()
        self._fill_writer.writeheader()

        self._signal_count = 0
        self._fill_count = 0

        logger.info(f"Trade logger opened: {signal_path.name}, {fill_path.name}")

    def end_session(self) -> None:
        """Flush and close output files. Call at end of session."""
        if self._signal_fh:
            self._signal_fh.close()
            self._signal_fh = None
        if self._fill_fh:
            self._fill_fh.close()
            self._fill_fh = None
        logger.info(
            f"Trade logger closed for {self._session_date}: "
            f"{self._signal_count} signals, {self._fill_count} fills."
        )

    # ------------------------------------------------------------------
    # Write methods
    # ------------------------------------------------------------------

    def log_signal(self, signal) -> None:
        """Log a StrategySignal to the signals CSV."""
        if self._signal_writer is None:
            logger.warning("log_signal called before begin_session — skipping.")
            return

        self._signal_writer.writerow({
            "session_date":       str(signal.session_date),
            "strategy_id":        signal.strategy_id,
            "ticker":             signal.ticker,
            "signal_type":        signal.signal_type,
            "direction":          signal.direction,
            "bar_time":           signal.bar_time.isoformat(),
            "bar_index":          signal.bar_index,
            "trigger_price":      round(signal.trigger_price, 6),
            "session_open_price": round(signal.session_open_price, 6),
            "drive_magnitude_pct": round(signal.drive_magnitude_pct, 4),
            "v4_early_reclaim":   signal.v4_early_reclaim,
        })
        self._signal_fh.flush()
        self._signal_count += 1

    def log_fill(self, fill) -> None:
        """Log a Fill (entry or exit) to the fills CSV."""
        if self._fill_writer is None:
            logger.warning("log_fill called before begin_session — skipping.")
            return

        self._fill_writer.writerow({
            "session_date":    str(fill.session_date),
            "strategy_id":     fill.strategy_id,
            "ticker":          fill.ticker,
            "fill_type":       fill.fill_type,
            "direction":       fill.direction,
            "fill_time":       fill.fill_time.isoformat(),
            "fill_price":      round(fill.fill_price, 6),
            "fill_price_raw":  round(fill.fill_price_raw, 6),
            "shares":          fill.shares,
            "slippage_bp":     fill.slippage_bp,
            "simulated":       fill.simulated,
        })
        self._fill_fh.flush()
        self._fill_count += 1

    def log_daily_summary(self, summary: dict) -> None:
        """Write end-of-day portfolio summary JSON."""
        if self._session_date is None:
            return

        date_str = self._session_date.strftime("%Y_%m_%d")
        summary_path = self._session_dir / f"daily_summary__{date_str}.json"

        summary["signals_emitted"] = self._signal_count
        summary["fills_recorded"] = self._fill_count
        summary["logged_at"] = datetime.now().isoformat()

        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, default=str)

        logger.info(f"Daily summary written: {summary_path.name}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _session_fh_open(self) -> bool:
        return self._signal_fh is not None or self._fill_fh is not None
