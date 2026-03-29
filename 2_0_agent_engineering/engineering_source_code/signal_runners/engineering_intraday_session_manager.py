"""
engineering_intraday_session_manager.py

Intraday bar accumulator and session state manager for the intraday_same_day track.
Phase: phase_e2

Drives the frozen V1 strategy incrementally — bar-by-bar as live Alpaca 1-minute
bars arrive — instead of as a single EOD batch.

Design contract:
    This module is an orchestration layer only. It does not add strategy logic,
    modify risk rules, change the broker adapter, or alter any output format.
    All six engineering layers are wired in the same architectural roles as phase_e0/e1.

Architecture roles (unchanged):
    RegimeGate      : called once at open_session()
    PortfolioRisk   : begin_session() at open; incremental evaluate/record/update each bar
    Broker adapter  : fill_entry() / fill_exit() per event (dry-run or live)
    TradeLogger     : begin_session() at open; log_signal / log_fill as events fire; close at EOD
    Strategy module : reset_session() at open (lazily, on first bar); on_bar() per new bar

Duplicate-entry prevention — three independent guards in order:
    1. strategy._entry_fired (frozen module fires at most once per session)
    2. self._entry_fills dict (update() skips signal detection for tickers already in position)
    3. risk_engine.evaluate_entry() returns rejected("already_in_position") if somehow reached

Flat-by-close:
    update() never creates exit fills. Exits happen only in force_eod_exit().
    The caller (daily launcher) must call force_eod_exit() at EOD before close_session().

Strategy module initialization (lazy):
    reset_session() requires the session open price (first bar's open).
    Modules are initialized the first time update() receives bars for a ticker,
    using the first available bar's open as the session open price.
    This handles start times that predate the 09:30 bar.

Usage (from engineering_daily_launcher_intraday_same_day.py):
    manager = IntradaySessionManager(gate, risk, broker, tlogger, portfolio_usd, session_date)

    regime_ok = manager.open_session(candidate_tickers)
    if not regime_ok:
        summary = manager.close_session()
        return summary

    while not eod:
        bar_data = feed.fetch_session_bars(tickers, session_date)
        cycle = manager.update(bar_data)
        time.sleep(60)

    final_bars = feed.fetch_session_bars(tickers, session_date)
    manager.force_eod_exit(final_bars)
    summary = manager.close_session()
"""

from __future__ import annotations

import datetime
import logging
from typing import Dict, List, Optional, Set

import pandas as pd

from integrated_strategy_modules.intraday_same_day.failed_opening_drive_and_reclaim__child_001_v1.engineering_strategy_module__failed_opening_drive_and_reclaim__child_001_v1 import (
    FailedOpeningDriveReclaimV1,
    STRATEGY_ID,
)

logger = logging.getLogger(__name__)

_SESSION_START = "09:30"
_SESSION_END   = "15:59"
_EXIT_TIME     = datetime.time(15, 59)


# ---------------------------------------------------------------------------
# Module-level helper — matches _extract_session_bars in signal runner exactly
# ---------------------------------------------------------------------------

def _extract_session_bars(df: pd.DataFrame, session_date: datetime.date) -> pd.DataFrame:
    """
    Slice a ticker DataFrame to regular session hours (09:30–15:59 ET)
    for a specific session date.

    Ensures the index is tz-aware in America/New_York before slicing.
    """
    if df.index.tz is None:
        df = df.copy()
        df.index = df.index.tz_localize("UTC").tz_convert("America/New_York")
    elif str(df.index.tz) != "America/New_York":
        df = df.copy()
        df.index = df.index.tz_convert("America/New_York")
    day_mask = df.index.date == session_date
    day_df = df.loc[day_mask]
    if day_df.empty:
        return day_df
    return day_df.between_time(_SESSION_START, _SESSION_END)


# ---------------------------------------------------------------------------
# Intraday session manager
# ---------------------------------------------------------------------------

class IntradaySessionManager:
    """
    Intraday bar accumulator and session state manager.

    Drives the 6-layer architecture bar-by-bar against live Alpaca data.
    Each update() call processes only bars that are newer than the last
    processed bar per ticker — preventing any bar from being fed twice.
    """

    def __init__(
        self,
        regime_gate,
        risk_engine,
        broker,
        trade_logger,
        portfolio_value_usd: float,
        session_date: datetime.date,
    ) -> None:
        """
        Parameters:
            regime_gate        : RegimeGate instance
            risk_engine        : PortfolioRiskControls instance
            broker             : AlpacaPaperAdapter (or PaperFillSimulator) instance
            trade_logger       : TradeLogger instance
            portfolio_value_usd: session starting portfolio value
            session_date       : the trading date
        """
        self._regime_gate = regime_gate
        self._risk = risk_engine
        self._broker = broker
        self._tlogger = trade_logger
        self._portfolio_usd = portfolio_value_usd
        self._session_date = session_date

        # Per-ticker live state
        self._candidate_tickers: List[str] = []
        self._strategy_instances: Dict[str, FailedOpeningDriveReclaimV1] = {}
        self._ineligible_tickers: Set[str] = set()       # failed price filter at reset_session
        self._last_bar_time: Dict[str, Optional[pd.Timestamp]] = {}
        self._entry_fills: Dict[str, object] = {}        # ticker -> Fill for open positions

        # Session-level flags
        self._session_open: bool = False
        self._regime_ok: bool = False
        self._regime_label: str = "unknown"

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def open_session(self, candidate_tickers: List[str]) -> bool:
        """
        Check regime, open trade logger, initialise risk engine.
        Strategy modules are initialised lazily on the first update() with bars.

        Parameters:
            candidate_tickers : tickers to monitor this session

        Returns:
            True  if regime is non-bearish (gate open — session is live).
            False if regime gate is closed (bearish month — no trades today).
                  The logger is still opened in either case so the daily skip
                  is recorded in the daily_summary JSON.
        """
        self._candidate_tickers = list(candidate_tickers)

        # Layer 1: regime gate
        self._regime_ok = self._regime_gate.is_non_bearish(self._session_date)
        self._regime_label = self._regime_gate.get_regime_label(self._session_date)

        # Always open logger and risk engine (regime-closed days still get a summary)
        self._tlogger.begin_session(self._session_date)
        self._risk.begin_session(self._session_date, self._portfolio_usd)

        self._session_open = True

        if not self._regime_ok:
            logger.info(
                f"Session {self._session_date}: REGIME GATE CLOSED "
                f"({self._regime_label}) — no trades today."
            )
        else:
            logger.info(
                f"Session {self._session_date}: regime = {self._regime_label} "
                f"— gate open. Monitoring {len(candidate_tickers)} tickers."
            )

        return self._regime_ok

    def update(self, bar_data: Dict[str, pd.DataFrame]) -> dict:
        """
        Process all bars that have arrived since the last update() call.

        For each candidate ticker:
          - Initialise the strategy module lazily on first bars (price filter applied).
          - Filter to bars newer than self._last_bar_time[ticker].
          - Feed new bars one-by-one to the frozen strategy module.
          - If a signal fires: evaluate risk, execute fill (dry-run or live), log.
          - For tickers already in a position: call update_unrealized() per bar.

        Parameters:
            bar_data : Dict[ticker, DataFrame] as returned by AlpacaMinuteBarFeed.

        Returns:
            dict with keys: new_bars_processed, new_signals, new_entries
        """
        if not self._session_open or not self._regime_ok:
            return {"new_bars_processed": 0, "new_signals": 0, "new_entries": 0}

        total_new_bars = 0
        new_signals = 0
        new_entries = 0

        for ticker in self._candidate_tickers:

            if ticker in self._ineligible_tickers:
                continue

            df = bar_data.get(ticker)
            if df is None or df.empty:
                continue

            session_df = _extract_session_bars(df, self._session_date)
            if session_df.empty:
                continue

            # ---- Lazy strategy module initialisation --------------------------------
            if ticker not in self._strategy_instances:
                session_open_price = float(session_df.iloc[0]["open"])
                module = FailedOpeningDriveReclaimV1()
                eligible = module.reset_session(ticker, session_open_price, self._session_date)
                if not eligible:
                    # Price outside $5–$20 — skip for the whole session
                    self._ineligible_tickers.add(ticker)
                    logger.debug(
                        f"[{ticker}] ineligible (session open ${session_open_price:.4f} "
                        f"outside $5–$20) — skipping."
                    )
                    continue
                self._strategy_instances[ticker] = module
                self._last_bar_time[ticker] = None
                logger.debug(
                    f"[{ticker}] strategy module initialised "
                    f"(session open ${session_open_price:.4f})"
                )

            module = self._strategy_instances[ticker]

            # ---- Filter to new bars only --------------------------------------------
            last_time = self._last_bar_time[ticker]
            if last_time is not None:
                new_bars = session_df[session_df.index > last_time]
            else:
                new_bars = session_df   # first update for this ticker: all bars

            if new_bars.empty:
                continue

            # ---- Feed new bars in strict chronological order -----------------------
            for bar_time, bar in new_bars.iterrows():
                bar_close = float(bar["close"])
                total_new_bars += 1

                # Guard 2: ticker already in position — update unrealized P&L, skip signal
                if ticker in self._entry_fills:
                    self._risk.update_unrealized(ticker, bar_close)
                    continue

                # Feed bar to the frozen strategy module
                # Guard 1: strategy module's _entry_fired flag prevents duplicate signals
                signal = module.on_bar(bar_time=bar_time, bar_close=bar_close)

                if signal is None:
                    continue

                # Signal fired — log immediately (files are flushed after each write)
                self._tlogger.log_signal(signal)
                new_signals += 1

                # Layer 2 (risk engine): guard 3 + position sizing
                risk_decision = self._risk.evaluate_entry(
                    ticker=ticker,
                    entry_price=signal.trigger_price,
                    session_date=self._session_date,
                )

                if not risk_decision.approved:
                    logger.info(
                        f"Entry BLOCKED by risk engine: {ticker} "
                        f"— {risk_decision.reason}"
                    )
                    continue

                # Layer 3 (broker): fill entry (dry-run logs; live submits order)
                entry_fill = self._broker.fill_entry(
                    ticker=ticker,
                    bar_time=bar_time,
                    bar_close=signal.trigger_price,
                    shares=risk_decision.position_size_shares,
                    session_date=self._session_date,
                    strategy_id=signal.strategy_id,
                )

                self._risk.record_entry(ticker, entry_fill.fill_price, entry_fill.shares)
                self._tlogger.log_fill(entry_fill)
                self._entry_fills[ticker] = entry_fill
                new_entries += 1

            # Always advance the watermark to the last bar of this batch
            self._last_bar_time[ticker] = new_bars.index[-1]

        return {
            "new_bars_processed": total_new_bars,
            "new_signals": new_signals,
            "new_entries": new_entries,
        }

    def force_eod_exit(self, bar_data: Dict[str, pd.DataFrame]) -> None:
        """
        Force-close all open positions at 15:59 ET (or last available bar as fallback).

        Must be called by the launcher at 16:05 ET after the final bar fetch.
        This is the only place where exit fills are created — never during update().
        Preserves the flat-by-close guarantee from the frozen V1 strategy.

        Parameters:
            bar_data : full-day bar data from AlpacaMinuteBarFeed (should include 15:59 bar)
        """
        open_tickers = list(self._entry_fills.keys())

        if not open_tickers:
            logger.info(
                f"Session {self._session_date}: EOD — no open positions to close."
            )
            return

        logger.info(
            f"Session {self._session_date}: EOD — closing "
            f"{len(open_tickers)} open position(s)."
        )

        for ticker in open_tickers:
            entry_fill = self._entry_fills[ticker]

            df = bar_data.get(ticker)
            if df is None or df.empty:
                logger.warning(
                    f"EOD exit: no bar data for {ticker} — position NOT closed. "
                    f"Check Alpaca Paper account for open position."
                )
                continue

            session_df = _extract_session_bars(df, self._session_date)
            if session_df.empty:
                logger.warning(
                    f"EOD exit: no session bars for {ticker} — position NOT closed. "
                    f"Check Alpaca Paper account for open position."
                )
                continue

            # Use 15:59 bar; fall back to last available session bar
            exit_bars = session_df[session_df.index.time == _EXIT_TIME]
            if not exit_bars.empty:
                exit_time = exit_bars.index[0]
                exit_close = float(exit_bars.iloc[0]["close"])
            else:
                exit_time = session_df.index[-1]
                exit_close = float(session_df.iloc[-1]["close"])
                logger.warning(
                    f"EOD exit: no 15:59 bar for {ticker} — "
                    f"using last available bar at {exit_time.time()}"
                )

            exit_fill = self._broker.fill_exit(
                ticker=ticker,
                bar_time=exit_time,
                bar_close=exit_close,
                shares=entry_fill.shares,
                session_date=self._session_date,
                strategy_id=entry_fill.strategy_id,
            )

            self._risk.record_exit(ticker, exit_fill.fill_price)
            self._tlogger.log_fill(exit_fill)

        # Clear the open-position tracker
        self._entry_fills.clear()

    def close_session(self) -> dict:
        """
        Write the daily summary JSON and close all logger file handles.

        Must be called after force_eod_exit() (or directly if regime was closed).
        Returns the same summary dict structure as IntradaySameDaySignalRunner.
        """
        summary = self._risk.get_daily_summary()
        summary["strategy_id"] = STRATEGY_ID
        summary["regime_label"] = self._regime_label
        summary["trades_blocked_by_regime"] = not self._regime_ok

        self._tlogger.log_daily_summary(summary)
        self._tlogger.end_session()

        logger.info(
            f"=== Session {self._session_date} complete: "
            f"trades={summary.get('total_trades_entered', 0)}, "
            f"pnl={summary.get('total_pnl_pct', 0.0):+.3f}% ==="
        )
        return summary

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def open_position_count(self) -> int:
        """Number of open positions currently held."""
        return len(self._entry_fills)

    def initialized_ticker_count(self) -> int:
        """Number of tickers with an active strategy module this session."""
        return len(self._strategy_instances)

    @property
    def regime_label(self) -> str:
        """Regime label for today's session ('non_bearish', 'bearish', 'unknown')."""
        return self._regime_label
