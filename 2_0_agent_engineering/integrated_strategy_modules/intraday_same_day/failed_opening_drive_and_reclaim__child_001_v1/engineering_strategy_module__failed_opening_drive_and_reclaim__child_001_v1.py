"""
engineering_strategy_module__failed_opening_drive_and_reclaim__child_001_v1.py

Track:   intraday_same_day
Family:  failed_opening_drive_and_reclaim
Branch:  child_001 (parent_002__child_001__price_filtered_regime_gated)
Variant: V1

Frozen on: 2026-03-25
Phase:     phase_e0 (paper trading only)

This module implements the locked V1 rule specification exactly as defined in:
  1_0_strategy_research/research_source_code/strategy_families/intraday_same_day/
  failed_opening_drive_and_reclaim/frozen_survivors/
  frozen_survivor__child_001_v1__failed_opening_drive_and_reclaim__2026_03_25.md

DO NOT modify the strategy logic without reopening research and re-validating.
All constants below match the research reference implementation exactly.

Interface:
    module = FailedOpeningDriveReclaimV1()
    eligible = module.reset_session(ticker, session_open_price, session_date)
    signal = module.on_bar(bar_time, bar_close)   # returns StrategySignal or None

This module is stateful per ticker per session. Call reset_session() at session
open for each candidate ticker, then call on_bar() for each 1-minute bar in
chronological order. The module returns a StrategySignal exactly once per session
(when the reclaim trigger fires) and is silent thereafter.

No I/O, no external calls, no logging output — all of that lives in the signal runner.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional


# ---------------------------------------------------------------------------
# Locked constants — match research reference implementation exactly
# ---------------------------------------------------------------------------

_DRIVE_WINDOW_BARS: int = 30        # bars 1-30 (09:30-09:59 ET on 1-minute data)
_DRIVE_MAGNITUDE_PCT: float = 2.0   # close of bar 30 must be >= 2.0% below session open
_DRIVE_FLAT_THRESH: float = 0.10    # minimum downward move to count at all (pre-filter)
_RECLAIM_START_BAR: int = 31        # reclaim detection begins at bar 31
_V4_EARLY_MAX_BAR: int = 60         # V4 overlay: reclaim at or before bar 60
_PRICE_MIN: float = 5.00            # session open must be >= $5.00
_PRICE_MAX: float = 20.00           # session open must be <= $20.00

STRATEGY_ID: str = "failed_opening_drive_and_reclaim__child_001_v1"


# ---------------------------------------------------------------------------
# Signal dataclass
# ---------------------------------------------------------------------------

@dataclass
class StrategySignal:
    """
    Emitted by the strategy module when the reclaim trigger fires.

    signal_type is always 'ENTRY' for this module — exits are managed by the
    signal runner (time-based at 15:59 ET), not by the strategy module.

    v4_early_reclaim annotates whether this event qualifies as a V4 early-reclaim
    event (reclaim bar <= 60). Used by the risk engine for optional sizing overlay.
    """
    ticker: str
    strategy_id: str
    signal_type: str            # always 'ENTRY'
    direction: str              # always 'LONG'
    bar_time: datetime          # bar open time of the reclaim bar (ET)
    trigger_price: float        # close of the reclaim bar = intended entry price
    session_open_price: float
    session_date: date
    bar_index: int              # 1-indexed bar number within the session
    drive_magnitude_pct: float  # actual drive magnitude (negative number, e.g. -2.47)
    v4_early_reclaim: bool      # True if bar_index <= 60
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Strategy module
# ---------------------------------------------------------------------------

class FailedOpeningDriveReclaimV1:
    """
    Frozen strategy detector for failed_opening_drive_and_reclaim__child_001_v1.

    Stateful per ticker per session. Safe to instantiate once and reuse across
    sessions by calling reset_session() before each new session.

    Drive measurement (matches research code exactly):
        drive_magnitude_pct = (close_bar30 - session_open) / session_open * 100
        Condition: drive_magnitude_pct <= -2.0%

    This uses the close of bar 30 as the drive end reference, NOT the intraday
    minimum low. This matches the research reference implementation.
    """

    STRATEGY_ID = STRATEGY_ID

    def __init__(self) -> None:
        self._ticker: Optional[str] = None
        self._session_date: Optional[date] = None
        self._session_open: float = 0.0
        self._bar_index: int = 0
        self._drive_confirmed: bool = False
        self._drive_magnitude_pct: float = 0.0
        self._entry_fired: bool = False

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def reset_session(
        self,
        ticker: str,
        session_open_price: float,
        session_date: date,
    ) -> bool:
        """
        Prepare the module for a new session on a given ticker.

        Returns True if the ticker passes the price filter and the module is
        ready to receive bars. Returns False if ineligible (price outside $5-$20).

        Call this at 09:30 ET for each candidate ticker before feeding bars.
        """
        self._ticker = None
        self._session_date = None
        self._session_open = 0.0
        self._bar_index = 0
        self._drive_confirmed = False
        self._drive_magnitude_pct = 0.0
        self._entry_fired = False

        if not (_PRICE_MIN <= session_open_price <= _PRICE_MAX):
            return False

        self._ticker = ticker
        self._session_date = session_date
        self._session_open = session_open_price
        return True

    def on_bar(self, bar_time: datetime, bar_close: float) -> Optional[StrategySignal]:
        """
        Process a single 1-minute bar. Returns a StrategySignal if the entry
        trigger fires on this bar; returns None otherwise.

        Parameters:
            bar_time  : bar open time (DatetimeIndex value, America/New_York)
            bar_close : close price of this bar

        Must be called in strict chronological order starting from bar 1 (09:30).
        Do not call after entry has fired — check is_active() first if needed.
        """
        if self._ticker is None or self._entry_fired:
            return None

        self._bar_index += 1

        # ---- Drive window: bars 1-30 ----------------------------------------
        if self._bar_index <= _DRIVE_WINDOW_BARS:
            # At end of drive window, evaluate drive condition from bar 30 close
            if self._bar_index == _DRIVE_WINDOW_BARS:
                mag = (bar_close - self._session_open) / self._session_open * 100.0
                # Must be a downward drive (negative) and exceed flat threshold
                if mag >= -_DRIVE_FLAT_THRESH:
                    return None  # price went sideways or up — no setup
                if abs(mag) < _DRIVE_MAGNITUDE_PCT:
                    return None  # drive too small
                self._drive_confirmed = True
                self._drive_magnitude_pct = mag
            return None

        # ---- Post-drive window: bar 31+ -------------------------------------
        if not self._drive_confirmed:
            return None

        # Reclaim condition: bar close >= session open
        if bar_close < self._session_open:
            return None

        # Trigger fires
        self._entry_fired = True
        v4_early = self._bar_index <= _V4_EARLY_MAX_BAR

        return StrategySignal(
            ticker=self._ticker,
            strategy_id=self.STRATEGY_ID,
            signal_type="ENTRY",
            direction="LONG",
            bar_time=bar_time,
            trigger_price=bar_close,
            session_open_price=self._session_open,
            session_date=self._session_date,
            bar_index=self._bar_index,
            drive_magnitude_pct=self._drive_magnitude_pct,
            v4_early_reclaim=v4_early,
        )

    def is_active(self) -> bool:
        """True if a ticker is loaded and the entry has not yet fired."""
        return self._ticker is not None and not self._entry_fired

    def is_drive_confirmed(self) -> bool:
        """True if the drive condition was confirmed at bar 30."""
        return self._drive_confirmed

    def bars_processed(self) -> int:
        """Number of bars processed so far this session."""
        return self._bar_index
