"""
engineering_broker_alpaca_paper_adapter.py

Alpaca paper-trading broker adapter for phase_e1.

Exposes the same interface as PaperFillSimulator (fill_entry / fill_exit)
so it can be swapped into the signal runner without touching any other layer.

Safe by default:
    submit_orders = False  →  dry-run mode: logs what would be submitted,
                              returns a Fill with simulated=True.
    submit_orders = True   →  actually POSTs market orders to Alpaca Paper.
                              Requires ALPACA_API_KEY / ALPACA_API_SECRET env vars
                              and the Alpaca paper endpoint to be reachable.

Fill price model (same as PaperFillSimulator):
    Even when orders are submitted, the logged fill_price uses bar_close ±
    leg slippage (matching the research model). Actual Alpaca market-order fills
    may differ slightly. The Alpaca order ID is stored in the log but not in
    the Fill dataclass (which is shared with the paper simulator path).

Usage:
    broker = AlpacaPaperAdapter(
        api_key="...",
        api_secret="...",
        paper_base_url="https://paper-api.alpaca.markets",
        roundtrip_slippage_bp=10,
        submit_orders=False,         # SAFE DEFAULT
    )
    entry_fill = broker.fill_entry(ticker, bar_time, bar_close, shares, ...)
    exit_fill  = broker.fill_exit(ticker, bar_time, bar_close, shares, ...)
"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

import requests

# Import the shared Fill dataclass from the paper simulator
from engineering_source_code.broker_execution_adapters.engineering_broker_paper_fill_simulator import (
    Fill,
)

logger = logging.getLogger(__name__)

# Alpaca REST endpoints (relative to paper_base_url)
_ORDERS_ENDPOINT = "/v2/orders"
_ACCOUNT_ENDPOINT = "/v2/account"
_POSITIONS_ENDPOINT = "/v2/positions"

# Session close — do not submit new orders after this ET time
_SESSION_CLOSE = datetime.time(16, 0)


class AlpacaPaperAdapter:
    """
    Broker adapter that submits market orders to Alpaca Paper Trading.

    Implements the same fill_entry / fill_exit interface as PaperFillSimulator.
    When submit_orders=False (default), behaves identically to PaperFillSimulator
    but logs the intended order so you can verify logic without risk.
    """

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        paper_base_url: str = "https://paper-api.alpaca.markets",
        roundtrip_slippage_bp: float = 10.0,
        submit_orders: bool = False,
        request_timeout: int = 10,
    ) -> None:
        """
        Parameters:
            api_key               : Alpaca API key (from ALPACA_API_KEY env var)
            api_secret            : Alpaca API secret (from ALPACA_API_SECRET env var)
            paper_base_url        : Alpaca paper trading base URL
            roundtrip_slippage_bp : roundtrip slippage in basis points for fill
                                    price logging (matches research model)
            submit_orders         : if True, POST orders to Alpaca Paper;
                                    if False (default), dry-run only
            request_timeout       : HTTP timeout in seconds
        """
        self.paper_base_url = paper_base_url.rstrip("/")
        self.roundtrip_slippage_bp = roundtrip_slippage_bp
        self.submit_orders = submit_orders
        self.request_timeout = request_timeout

        self._leg_slippage_bp = roundtrip_slippage_bp / 2.0
        self._leg_slippage_pct = self._leg_slippage_bp / 10_000.0

        self._headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        mode = "LIVE-SUBMIT" if submit_orders else "DRY-RUN"
        logger.info(f"AlpacaPaperAdapter initialized — mode={mode}, slippage={roundtrip_slippage_bp}bp")

    # ------------------------------------------------------------------
    # Broker interface (matches PaperFillSimulator exactly)
    # ------------------------------------------------------------------

    def fill_entry(
        self,
        ticker: str,
        bar_time: datetime.datetime,
        bar_close: float,
        shares: int,
        session_date: datetime.date,
        strategy_id: str,
        direction: str = "LONG",
    ) -> Fill:
        """
        Submit (or log) a market buy order.

        Returns a Fill with fill_price = bar_close + entry slippage.
        When submit_orders=True, also POSTs a market buy to Alpaca Paper.
        """
        fill_price = bar_close * (1.0 + self._leg_slippage_pct)

        if self.submit_orders:
            self._submit_order(ticker, "buy", shares, bar_time)
        else:
            logger.info(
                f"[DRY-RUN] ENTRY {ticker} {shares}sh @ ~${fill_price:.4f} "
                f"(close=${bar_close:.4f} + {self._leg_slippage_bp:.1f}bp) — "
                f"would submit market buy to Alpaca Paper"
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
            simulated=not self.submit_orders,
            slippage_bp=self._leg_slippage_bp,
        )

    def fill_exit(
        self,
        ticker: str,
        bar_time: datetime.datetime,
        bar_close: float,
        shares: int,
        session_date: datetime.date,
        strategy_id: str,
        direction: str = "LONG",
    ) -> Fill:
        """
        Submit (or log) a market sell order.

        Returns a Fill with fill_price = bar_close - exit slippage.
        When submit_orders=True, also POSTs a market sell to Alpaca Paper.
        """
        fill_price = bar_close * (1.0 - self._leg_slippage_pct)

        if self.submit_orders:
            # Only submit exit if market is still open
            now_et = _now_et()
            if now_et.time() < _SESSION_CLOSE:
                self._submit_order(ticker, "sell", shares, bar_time)
            else:
                logger.warning(
                    f"Session closed — skipping Alpaca exit order for {ticker}. "
                    f"Check Alpaca Paper account for any open positions."
                )
        else:
            logger.info(
                f"[DRY-RUN] EXIT {ticker} {shares}sh @ ~${fill_price:.4f} "
                f"(close=${bar_close:.4f} - {self._leg_slippage_bp:.1f}bp) — "
                f"would submit market sell to Alpaca Paper"
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
            simulated=not self.submit_orders,
            slippage_bp=self._leg_slippage_bp,
        )

    # ------------------------------------------------------------------
    # Connectivity validation
    # ------------------------------------------------------------------

    def validate_connectivity(self) -> dict:
        """
        Verify Alpaca Paper account access.

        Returns dict with 'ok' (bool), 'message' (str), and optional
        'account_status', 'buying_power' fields on success.
        """
        try:
            resp = self._get(_ACCOUNT_ENDPOINT)
            return {
                "ok": True,
                "message": "Alpaca Paper account access confirmed.",
                "account_status": resp.get("status"),
                "buying_power": resp.get("buying_power"),
                "portfolio_value": resp.get("portfolio_value"),
            }
        except Exception as exc:
            return {"ok": False, "message": str(exc), "error": type(exc).__name__}

    def get_open_positions(self) -> list:
        """Return list of open Alpaca Paper positions (raw API dicts)."""
        try:
            return self._get(_POSITIONS_ENDPOINT)
        except Exception as exc:
            logger.error(f"Failed to fetch open positions: {exc}")
            return []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _submit_order(
        self,
        ticker: str,
        side: str,
        qty: int,
        bar_time: datetime.datetime,
    ) -> Optional[dict]:
        """POST a market day order to Alpaca Paper. Returns order dict or None."""
        payload = {
            "symbol": ticker,
            "qty": str(qty),
            "side": side,
            "type": "market",
            "time_in_force": "day",
        }
        try:
            response = self._post(_ORDERS_ENDPOINT, payload)
            order_id = response.get("id", "unknown")
            status = response.get("status", "unknown")
            logger.info(
                f"ALPACA ORDER SUBMITTED: {side.upper()} {qty}sh {ticker} "
                f"| order_id={order_id} status={status} bar_time={bar_time}"
            )
            return response
        except requests.HTTPError as exc:
            logger.error(
                f"Alpaca order submission FAILED for {side} {ticker}: "
                f"HTTP {exc.response.status_code} — {exc.response.text}"
            )
            return None
        except Exception as exc:
            logger.error(f"Alpaca order submission FAILED for {side} {ticker}: {exc}")
            return None

    def _get(self, endpoint: str, params: Optional[dict] = None) -> dict:
        url = self.paper_base_url + endpoint
        response = requests.get(
            url, headers=self._headers, params=params, timeout=self.request_timeout
        )
        response.raise_for_status()
        return response.json()

    def _post(self, endpoint: str, payload: dict) -> dict:
        url = self.paper_base_url + endpoint
        response = requests.post(
            url, headers=self._headers, json=payload, timeout=self.request_timeout
        )
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Timezone helper
# ---------------------------------------------------------------------------

def _get_et_tz():
    """Return America/New_York tzinfo, trying zoneinfo then pytz then UTC fallback."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("America/New_York")
    except ImportError:
        pass
    try:
        import pytz
        return pytz.timezone("America/New_York")
    except ImportError:
        pass
    logger.warning("Neither zoneinfo nor pytz available — using UTC for session-close check.")
    return datetime.timezone.utc


# Cache the tz object to avoid repeated imports
_ET_TZ = _get_et_tz()


def _now_et() -> datetime.datetime:
    """Return current time as a timezone-aware ET datetime."""
    return datetime.datetime.now(datetime.timezone.utc).astimezone(_ET_TZ)
