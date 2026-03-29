"""
engineering_broker_paper_fill_simulator.py

Paper fill simulator for phase_e0 (paper trading / replay mode).

Fill model:
    Entry fill price = close of the reclaim bar
    Exit fill price  = close of the 15:59 ET bar
    Both adjusted by configurable slippage.

Slippage model:
    Roundtrip slippage in basis points is split evenly: half on entry (adverse),
    half on exit (adverse). For a long position:
        Entry: fill_price = bar_close * (1 + entry_slippage_pct)  — pays more
        Exit:  fill_price = bar_close * (1 - exit_slippage_pct)   — receives less

    At 10bp roundtrip: +5bp on entry, -5bp on exit.
    This matches the slippage model used in the phase_r4 robustness validation.

Interface:
    broker = PaperFillSimulator(roundtrip_slippage_bp=10)
    entry_fill = broker.fill_entry(ticker, bar_time, bar_close, shares, ...)
    exit_fill  = broker.fill_exit(ticker, bar_time, bar_close, shares, ...)

This adapter exposes the same interface as the future live Alpaca adapter.
When ready for live trading, replace this module with
engineering_broker_alpaca_live_adapter.py — no other layers need to change.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, date

logger = logging.getLogger(__name__)


@dataclass
class Fill:
    """
    Represents a confirmed order fill (simulated or live).

    fill_price is the actual execution price including slippage.
    fill_price_raw is the bar close before slippage adjustment.
    """
    ticker: str
    fill_type: str              # 'ENTRY' | 'EXIT'
    direction: str              # 'LONG'
    fill_time: datetime         # bar open time of the fill bar (ET)
    fill_price: float           # execution price (after slippage)
    fill_price_raw: float       # bar close before slippage
    shares: int
    session_date: date
    strategy_id: str
    simulated: bool = True
    slippage_bp: float = 0.0    # per-leg slippage in basis points applied


class PaperFillSimulator:
    """
    Simulates order fills for paper trading and historical replay.

    No bid/ask model, no spread model, no partial fills in phase_e0.
    Fill = bar close ± configurable slippage. This is the same model
    used in phase_r4 slippage sensitivity analysis.
    """

    def __init__(self, roundtrip_slippage_bp: float = 0.0) -> None:
        """
        Parameters:
            roundtrip_slippage_bp : total roundtrip slippage in basis points.
                                    Split evenly: half on entry, half on exit.
                                    0 = no slippage (gross, matches research base case).
                                    10 = realistic for $5-$20 stocks with limit orders.
        """
        self.roundtrip_slippage_bp = roundtrip_slippage_bp
        self._leg_slippage_bp = roundtrip_slippage_bp / 2.0
        self._leg_slippage_pct = self._leg_slippage_bp / 10_000.0

    def fill_entry(
        self,
        ticker: str,
        bar_time: datetime,
        bar_close: float,
        shares: int,
        session_date: date,
        strategy_id: str,
        direction: str = "LONG",
    ) -> Fill:
        """
        Simulate an entry fill at the reclaim bar close.

        For a long entry: adverse slippage means we pay slightly above close.
        fill_price = bar_close * (1 + leg_slippage_pct)
        """
        fill_price = bar_close * (1.0 + self._leg_slippage_pct)

        logger.info(
            f"PAPER ENTRY: {ticker} {shares}sh @ ${fill_price:.4f} "
            f"(close=${bar_close:.4f} + {self._leg_slippage_bp:.1f}bp slippage)"
        )

        return Fill(
            ticker=ticker,
            fill_type="ENTRY",
            direction=direction,
            fill_time=bar_time,
            fill_price=round(fill_price, 6),
            fill_price_raw=bar_close,
            shares=shares,
            session_date=session_date,
            strategy_id=strategy_id,
            simulated=True,
            slippage_bp=self._leg_slippage_bp,
        )

    def fill_exit(
        self,
        ticker: str,
        bar_time: datetime,
        bar_close: float,
        shares: int,
        session_date: date,
        strategy_id: str,
        direction: str = "LONG",
    ) -> Fill:
        """
        Simulate an exit fill at the 15:59 ET bar close.

        For a long exit: adverse slippage means we receive slightly below close.
        fill_price = bar_close * (1 - leg_slippage_pct)
        """
        fill_price = bar_close * (1.0 - self._leg_slippage_pct)

        logger.info(
            f"PAPER EXIT: {ticker} {shares}sh @ ${fill_price:.4f} "
            f"(close=${bar_close:.4f} - {self._leg_slippage_bp:.1f}bp slippage)"
        )

        return Fill(
            ticker=ticker,
            fill_type="EXIT",
            direction=direction,
            fill_time=bar_time,
            fill_price=round(fill_price, 6),
            fill_price_raw=bar_close,
            shares=shares,
            session_date=session_date,
            strategy_id=strategy_id,
            simulated=True,
            slippage_bp=self._leg_slippage_bp,
        )
