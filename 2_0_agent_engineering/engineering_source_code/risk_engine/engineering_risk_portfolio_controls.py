"""
engineering_risk_portfolio_controls.py

Portfolio-level risk controls for the intraday_same_day engineering track.

Enforces:
    - Maximum number of open positions per session
    - Maximum position size as a percentage of portfolio value
    - Daily loss limit halt (halts new entries if total P&L drops below threshold)

IMPORTANT — no trade-level stops:
    This module does not implement intraday trade-level stops.
    Per the frozen research finding for child_001_v1, any intraday stop
    destroys the signal edge. Risk is managed entirely at the portfolio level.

    If a compliance-driven hard stop is ever required, add it here under
    'tail_guard_stop_pct' — a separate config key that is disabled by default.
    Do not add stop logic inside the strategy module.

Interface:
    risk = PortfolioRiskControls(portfolio_value_usd=50_000)
    risk.begin_session(session_date, portfolio_value_usd)
    decision = risk.evaluate_entry(ticker, entry_price, session_date)
    risk.record_entry(ticker, fill_price, shares)
    risk.update_unrealized(ticker, current_price)
    realized_pnl = risk.record_exit(ticker, exit_price)
    summary = risk.get_daily_summary()
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RiskDecision:
    """Result of evaluate_entry(). Check .approved before submitting a fill."""
    approved: bool
    ticker: str
    session_date: date
    reason: str
    position_size_shares: int
    position_size_usd: float


class PortfolioRiskControls:
    """
    Portfolio-level risk wrapper.

    Stateful per session. Call begin_session() at 09:30 ET to reset all
    intraday state. Designed to be shared across multiple strategy modules
    running in the same signal runner.
    """

    def __init__(
        self,
        portfolio_value_usd: float,
        max_open_positions: int = 5,
        max_position_size_pct: float = 0.10,
        daily_loss_limit_pct: float = -0.02,
        tail_guard_stop_pct: Optional[float] = None,
    ) -> None:
        """
        Parameters:
            portfolio_value_usd     : starting portfolio value for the session
            max_open_positions      : max simultaneous open positions (default 5)
            max_position_size_pct   : max single position as % of portfolio (default 10%)
            daily_loss_limit_pct    : halt new entries if total P&L pct drops below this
                                      (default -2.0% = halt if portfolio is down 2% intraday)
            tail_guard_stop_pct     : optional per-position emergency stop in % terms
                                      (None = disabled; never enable casually for V1)
        """
        self.portfolio_value_usd = portfolio_value_usd
        self.max_open_positions = max_open_positions
        self.max_position_size_pct = max_position_size_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct
        self.tail_guard_stop_pct = tail_guard_stop_pct

        self._session_date: Optional[date] = None
        self._open_positions: Dict[str, dict] = {}
        self._realized_pnl: float = 0.0
        self._unrealized_pnl: float = 0.0
        self._halted: bool = False
        self._total_trades: int = 0
        self._rejected_trades: int = 0

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def begin_session(self, session_date: date, portfolio_value_usd: float) -> None:
        """Reset all intraday state. Call at 09:30 ET before processing any tickers."""
        self._session_date = session_date
        self.portfolio_value_usd = portfolio_value_usd
        self._open_positions = {}
        self._realized_pnl = 0.0
        self._unrealized_pnl = 0.0
        self._halted = False
        self._total_trades = 0
        self._rejected_trades = 0
        logger.info(
            f"Risk engine session {session_date}: "
            f"portfolio=${portfolio_value_usd:,.0f}, "
            f"max_positions={self.max_open_positions}, "
            f"max_size={self.max_position_size_pct*100:.0f}%, "
            f"daily_loss_limit={self.daily_loss_limit_pct*100:.1f}%"
        )

    # ------------------------------------------------------------------
    # Entry evaluation
    # ------------------------------------------------------------------

    def evaluate_entry(
        self,
        ticker: str,
        entry_price: float,
        session_date: date,
    ) -> RiskDecision:
        """
        Evaluate whether a new long entry is permitted.

        Returns RiskDecision with approved=True and computed share count if all
        checks pass. Returns approved=False with a reason string if blocked.
        """
        def _reject(reason: str) -> RiskDecision:
            self._rejected_trades += 1
            logger.debug(f"Entry rejected: {ticker} — {reason}")
            return RiskDecision(
                approved=False, ticker=ticker, session_date=session_date,
                reason=reason, position_size_shares=0, position_size_usd=0.0,
            )

        if self._halted:
            return _reject("daily_loss_limit_halted")

        if ticker in self._open_positions:
            return _reject("already_in_position")

        if len(self._open_positions) >= self.max_open_positions:
            return _reject(
                f"max_open_positions_reached ({len(self._open_positions)}/{self.max_open_positions})"
            )

        # Check daily loss limit before allocating capital
        current_pnl_pct = self._total_pnl_pct()
        if current_pnl_pct <= self.daily_loss_limit_pct:
            self._halted = True
            return _reject(
                f"daily_loss_limit_breached ({current_pnl_pct*100:+.2f}% "
                f"<= {self.daily_loss_limit_pct*100:.1f}%)"
            )

        # Compute position size: floor to whole shares
        max_position_usd = self.portfolio_value_usd * self.max_position_size_pct
        shares = max(1, int(max_position_usd / entry_price))
        actual_usd = shares * entry_price

        return RiskDecision(
            approved=True,
            ticker=ticker,
            session_date=session_date,
            reason="approved",
            position_size_shares=shares,
            position_size_usd=actual_usd,
        )

    # ------------------------------------------------------------------
    # Position tracking
    # ------------------------------------------------------------------

    def record_entry(self, ticker: str, fill_price: float, shares: int) -> None:
        """Record a confirmed entry fill. Call after broker confirms the fill."""
        self._open_positions[ticker] = {
            "fill_price": fill_price,
            "shares": shares,
            "unrealized_pnl": 0.0,
        }
        self._total_trades += 1
        logger.info(
            f"Position opened: {ticker} {shares}sh @ ${fill_price:.4f} "
            f"[{len(self._open_positions)}/{self.max_open_positions} positions open]"
        )

    def update_unrealized(self, ticker: str, current_price: float) -> None:
        """
        Update unrealized P&L for an open position.
        Called per bar for each open position to keep the daily loss limit check current.
        """
        pos = self._open_positions.get(ticker)
        if pos is None:
            return
        pos["unrealized_pnl"] = (current_price - pos["fill_price"]) * pos["shares"]
        self._unrealized_pnl = sum(
            p["unrealized_pnl"] for p in self._open_positions.values()
        )

    def record_exit(self, ticker: str, exit_price: float) -> Optional[float]:
        """
        Record a confirmed exit fill. Returns realized P&L for this position.
        Returns None if the ticker is not found in open positions.
        """
        pos = self._open_positions.pop(ticker, None)
        if pos is None:
            logger.warning(f"record_exit called for {ticker} but no open position found.")
            return None

        realized = (exit_price - pos["fill_price"]) * pos["shares"]
        self._realized_pnl += realized

        # Recompute unrealized after removing the closed position
        self._unrealized_pnl = sum(
            p["unrealized_pnl"] for p in self._open_positions.values()
        )

        ret_pct = (exit_price - pos["fill_price"]) / pos["fill_price"] * 100
        pnl_port_pct = realized / self.portfolio_value_usd * 100
        logger.info(
            f"Position closed: {ticker} {pos['shares']}sh "
            f"entry=${pos['fill_price']:.4f} exit=${exit_price:.4f} "
            f"ret={ret_pct:+.3f}% pnl_trade=${realized:+.2f} ({pnl_port_pct:+.4f}% portfolio)"
        )
        return realized

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------

    def get_open_tickers(self) -> List[str]:
        return list(self._open_positions.keys())

    def is_halted(self) -> bool:
        return self._halted

    def get_daily_summary(self) -> dict:
        return {
            "session_date": str(self._session_date),
            "portfolio_value_usd": round(self.portfolio_value_usd, 2),
            "realized_pnl": round(self._realized_pnl, 4),
            "unrealized_pnl": round(self._unrealized_pnl, 4),
            "total_pnl": round(self._realized_pnl + self._unrealized_pnl, 4),
            "total_pnl_pct": round(self._total_pnl_pct() * 100, 4),
            "open_positions": len(self._open_positions),
            "total_trades_entered": self._total_trades,
            "rejected_entries": self._rejected_trades,
            "halted": self._halted,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _total_pnl_pct(self) -> float:
        if self.portfolio_value_usd == 0:
            return 0.0
        return (self._realized_pnl + self._unrealized_pnl) / self.portfolio_value_usd
