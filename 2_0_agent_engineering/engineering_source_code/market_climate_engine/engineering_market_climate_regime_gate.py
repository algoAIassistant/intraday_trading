"""
engineering_market_climate_regime_gate.py

Determines whether a session date's calendar month is non-bearish.

Non-bearish definition (from frozen research):
    Universe-average open-to-close return (OTC) for the calendar month > -0.10%.
    Computed from ~200-300 liquid U.S. common stocks.

In paper-trading mode (mode='precomputed'), loads a precomputed regime map CSV
produced by the research pipeline. Expected CSV columns:
    year_month        : period string, e.g. "2024-03"
    universe_avg_otc  : float, universe-average monthly OTC in percent
    regime            : "bearish" or "non_bearish"

Interface:
    gate = RegimeGate(mode="precomputed", regime_map_path="path/to/regime_map.csv")
    is_ok = gate.is_non_bearish(session_date)   # bool
    label = gate.get_regime_label(session_date)  # "non_bearish" | "bearish" | "unknown"

The gate defaults to CLOSED (bearish = no trades) for any month not in the map.
This is the safe default — unknown regime means no trades, not open trades.

Future mode: mode='live' will compute regime from a streaming universe feed.
Not implemented in phase_e0.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Dict, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

# Matches the research definition exactly
_BEARISH_THRESHOLD_PCT: float = -0.10

# Internal key type for the regime map lookup
_MonthKey = Tuple[int, int]   # (year, month)


class RegimeGate:
    """
    Market climate regime gate for the intraday_same_day track.

    Enforces the non-bearish month filter that is mandatory for
    failed_opening_drive_and_reclaim__child_001_v1 and expected to be
    mandatory for most future intraday_same_day strategy modules.
    """

    def __init__(
        self,
        mode: str = "precomputed",
        regime_map_path: Optional[str] = None,
        bearish_threshold_pct: float = _BEARISH_THRESHOLD_PCT,
    ) -> None:
        """
        Parameters:
            mode                : 'precomputed' — loads from CSV (phase_e0 default)
            regime_map_path     : path to regime map CSV; required when mode='precomputed'
            bearish_threshold_pct : monthly OTC below this = bearish (default -0.10)
        """
        if mode not in ("precomputed",):
            raise NotImplementedError(
                f"Regime mode '{mode}' not yet implemented. Use 'precomputed'."
            )

        self.mode = mode
        self.bearish_threshold_pct = bearish_threshold_pct
        self._regime_map: Dict[_MonthKey, bool] = {}  # True = non-bearish
        self._regime_otc: Dict[_MonthKey, float] = {}

        if regime_map_path:
            self._load_regime_map(regime_map_path)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_regime_map(self, path: str) -> None:
        """Load precomputed regime map from research output CSV."""
        p = Path(path)
        if not p.exists():
            logger.warning(
                f"Regime map not found at {path}. "
                "Gate will return CLOSED (bearish) for all dates until map is loaded."
            )
            return

        df = pd.read_csv(p)

        # Accept either column layout:
        #   year_month, universe_avg_otc, regime   (research output format)
        if "year_month" not in df.columns:
            raise ValueError(
                f"Regime map CSV must have a 'year_month' column. "
                f"Found columns: {list(df.columns)}"
            )

        loaded = 0
        for _, row in df.iterrows():
            key = self._parse_year_month(str(row["year_month"]))
            if key is None:
                continue
            otc = float(row["universe_avg_otc"])
            # Use explicit 'regime' column if present; otherwise compute from otc
            if "regime" in df.columns:
                is_non_bearish = str(row["regime"]).strip().lower() == "non_bearish"
            else:
                is_non_bearish = otc > self.bearish_threshold_pct
            self._regime_map[key] = is_non_bearish
            self._regime_otc[key] = otc
            loaded += 1

        non_bearish_count = sum(self._regime_map.values())
        bearish_count = loaded - non_bearish_count
        logger.info(
            f"Regime map loaded from {p.name}: "
            f"{loaded} months — {non_bearish_count} non-bearish, {bearish_count} bearish."
        )

    def set_regime_map_from_dict(self, regime_dict: Dict[_MonthKey, bool]) -> None:
        """
        Inject a regime map directly as {(year, month): is_non_bearish}.
        Useful for testing or programmatic construction.
        """
        self._regime_map = dict(regime_dict)

    # ------------------------------------------------------------------
    # Query interface
    # ------------------------------------------------------------------

    def is_non_bearish(self, session_date: date) -> bool:
        """
        Returns True if the session date's calendar month is non-bearish.
        Returns False (gate closed = no trades) for bearish months or
        for months not present in the regime map.

        The default-to-closed behavior is intentional: if regime data is
        unavailable for a month, the safe choice is to take no trades.
        """
        key = (session_date.year, session_date.month)
        result = self._regime_map.get(key)

        if result is None:
            logger.warning(
                f"No regime classification for "
                f"{session_date.year}-{session_date.month:02d}. "
                f"Defaulting to BEARISH (gate closed). "
                f"Extend the regime map to trade this month."
            )
            return False

        return result

    def get_regime_label(self, session_date: date) -> str:
        """Returns 'non_bearish', 'bearish', or 'unknown'."""
        key = (session_date.year, session_date.month)
        if key not in self._regime_map:
            return "unknown"
        return "non_bearish" if self._regime_map[key] else "bearish"

    def get_regime_otc(self, session_date: date) -> Optional[float]:
        """Returns the universe-average OTC% for the month, or None if unknown."""
        key = (session_date.year, session_date.month)
        return self._regime_otc.get(key)

    def months_loaded(self) -> int:
        """Number of months in the regime map."""
        return len(self._regime_map)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_year_month(s: str) -> Optional[_MonthKey]:
        """Parse 'YYYY-MM' or 'YYYY-MM-DD' period string into (year, month)."""
        try:
            parts = s.strip().split("-")
            return int(parts[0]), int(parts[1])
        except (ValueError, IndexError):
            logger.warning(f"Could not parse year_month value: '{s}'")
            return None
