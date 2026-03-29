"""
2_0_agent_engineering/engineering_build_operational_universe__gap_directional_trap__candidate_1_v1.py

Builds (or rebuilds) the module-specific operational universe for
gap_directional_trap__candidate_1_v1.

Purpose:
  The full shared master universe has ~4,700 tickers.
  For nightly refresh and scan, most of these will never reach the operator:
  the selection layer hard-filters to close 20-100 and ADV20 >= $2M.

  This script derives a conservative pre-filtered operational universe by reading
  existing daily parquets (no API calls) and applying slightly looser thresholds
  than the selection layer, so tickers near the boundary are preserved.

Conservative pre-filter thresholds (deliberately looser than selection layer):
  - close between 17.0 and 110.0   (selection layer uses 20-100)
  - ADV20 >= $1,500,000            (selection layer uses $2,000,000)
  - US common stock confirmed from shared metadata (type=CS, locale=us)

Looser thresholds preserve:
  - Tickers near the $20 lower boundary (stocks that may gap up into range)
  - Tickers near the $100 upper boundary (stocks that may pull back into range)
  - Tickers with slightly lower ADV that may have a high-volume signal day

Output:
  2_0_agent_engineering/engineering_configs/
    engineering_operational_universe__gap_directional_trap__candidate_1_v1.csv

  Columns: ticker, recent_close, adv20_dollar, adv20_sessions_available,
           last_parquet_date, built_date

Usage:
  python engineering_build_operational_universe__gap_directional_trap__candidate_1_v1.py

  # Dry run (print counts only, no file write)
  python engineering_build_operational_universe__gap_directional_trap__candidate_1_v1.py --dry-run

  # Force full-universe passthrough (disables pre-filter; writes all CS tickers with parquets)
  python engineering_build_operational_universe__gap_directional_trap__candidate_1_v1.py --no-filter

Notes:
  - Pure local computation — no API calls.
  - Safe to run at any time without MASSIVE_API_KEY.
  - Designed to run as Sub-task A0 within Stage 0 of the nightly pipeline
    (before the API-based daily refresh in Sub-task A).
  - The research-side shared universe is NOT modified.
  - For research or full-history backtests, continue using the shared universe.
"""

import argparse
import datetime
import sys
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Repo layout
# ---------------------------------------------------------------------------
ENG_ROOT  = Path(__file__).resolve().parent   # 2_0_agent_engineering/
REPO_ROOT = ENG_ROOT.parent                   # ai_trading_assistant/

METADATA_CSV = (
    REPO_ROOT
    / "0_1_shared_master_universe"
    / "shared_metadata"
    / "shared_master_metadata_us_common_stocks.csv"
)

DAILY_CACHE_DIR = (
    REPO_ROOT / "1_0_strategy_research" / "research_data_cache" / "daily"
)

OUTPUT_CSV = (
    ENG_ROOT
    / "engineering_configs"
    / "engineering_operational_universe__gap_directional_trap__candidate_1_v1.csv"
)

# ---------------------------------------------------------------------------
# Pre-filter thresholds (conservative — looser than selection layer)
# ---------------------------------------------------------------------------
PRICE_LO        = 17.0         # selection layer uses 20.0
PRICE_HI        = 110.0        # selection layer uses 100.0
ADV_DOLLAR_MIN  = 1_500_000.0  # selection layer uses 2_000_000.0
ADV_SESSIONS    = 20

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_parquet_path(ticker: str) -> Path:
    """Return the parquet path for a ticker, including Windows-reserved name guard."""
    _WIN_RESERVED = {
        "CON", "PRN", "AUX", "NUL",
        "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
        "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
    }
    stem = f"{ticker}__reserved" if ticker.upper() in _WIN_RESERVED else ticker
    return DAILY_CACHE_DIR / f"{stem}.parquet"


def _read_ticker_snapshot(ticker: str) -> dict | None:
    """
    Read the last available close and ADV20 for a ticker from its daily parquet.
    Returns None if parquet is missing or unreadable.
    """
    path = _get_parquet_path(ticker)
    if not path.exists():
        return None
    try:
        df = pd.read_parquet(path)
        if df.empty:
            return None
        df.index = pd.to_datetime(df.index).strftime("%Y-%m-%d")
        df = df[~df.index.duplicated(keep="last")].sort_index()
        last_row = df.iloc[-1]
        recent_close = float(last_row["close"])
        df["dollar_vol"] = df["close"].astype(float) * df["volume"].astype(float)
        tail = df["dollar_vol"].tail(ADV_SESSIONS)
        adv20 = float(tail.mean())
        sessions_available = int(len(tail))
        return {
            "ticker": ticker,
            "recent_close": round(recent_close, 4),
            "adv20_dollar": round(adv20, 0),
            "adv20_sessions_available": sessions_available,
            "last_parquet_date": df.index[-1],
        }
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_operational_universe(dry_run: bool = False, no_filter: bool = False) -> pd.DataFrame:
    """
    Build and (unless dry_run) write the operational universe CSV.

    Returns the resulting DataFrame.
    """
    print(f"\n{'='*66}", flush=True)
    print("  Operational universe builder", flush=True)
    print("  gap_directional_trap__candidate_1_v1", flush=True)
    print(f"  Metadata : {METADATA_CSV.name}", flush=True)
    print(f"  Daily dir: {DAILY_CACHE_DIR}", flush=True)
    if no_filter:
        print("  Mode     : --no-filter (all US CS tickers with parquets)", flush=True)
    else:
        print(
            f"  Pre-filter: close {PRICE_LO}-{PRICE_HI}, "
            f"ADV20 >= ${ADV_DOLLAR_MIN / 1_000_000:.1f}M",
            flush=True,
        )
    print(f"{'='*66}", flush=True)

    # -- Load metadata --
    if not METADATA_CSV.exists():
        print(f"[FAIL] Metadata CSV not found: {METADATA_CSV}")
        sys.exit(1)

    meta = pd.read_csv(METADATA_CSV, dtype={"ticker": str})
    cs_tickers = sorted(
        set(
            meta[(meta["type"] == "CS") & (meta["locale"] == "us")]["ticker"]
            .dropna()
            .str.strip()
            .str.upper()
        )
    )
    print(f"  US CS tickers in metadata: {len(cs_tickers)}", flush=True)

    # -- Read parquets --
    print("  Reading daily parquets (no API calls) ...", flush=True)
    snapshots = []
    count_missing = 0
    for ticker in cs_tickers:
        snap = _read_ticker_snapshot(ticker)
        if snap is None:
            count_missing += 1
        else:
            snapshots.append(snap)

    print(f"  Parquets read: {len(snapshots)}  |  missing: {count_missing}", flush=True)

    df = pd.DataFrame(snapshots)

    # -- Apply pre-filter --
    if no_filter:
        op = df.copy()
    else:
        op = df[
            (df["recent_close"] >= PRICE_LO)
            & (df["recent_close"] <= PRICE_HI)
            & (df["adv20_dollar"] >= ADV_DOLLAR_MIN)
        ].copy()

    # -- Annotate --
    op["built_date"] = datetime.date.today().isoformat()
    op = op.sort_values("ticker").reset_index(drop=True)

    # -- Summary --
    reduction_pct = (1.0 - len(op) / max(len(df), 1)) * 100
    print(f"\n  Full CS universe with parquets : {len(df)}", flush=True)
    print(f"  Operational universe size      : {len(op)}  ({reduction_pct:.0f}% reduction)", flush=True)

    if not no_filter:
        bins   = [0, 17, 20, 30, 50, 70, 100, 110, 999999]
        labels = ["<17", "17-20", "20-30", "30-50", "50-70", "70-100", "100-110", ">110"]
        df_all = df.copy()
        df_all["price_band"] = pd.cut(
            df_all["recent_close"], bins=bins, labels=labels, right=False, include_lowest=True
        )
        op_c = op.copy()
        op_c["price_band"] = pd.cut(
            op_c["recent_close"], bins=bins, labels=labels, right=False, include_lowest=True
        )
        print("\n  Price distribution (op universe):", flush=True)
        for label in ["17-20", "20-30", "30-50", "50-70", "70-100", "100-110"]:
            n = int((op_c["price_band"] == label).sum())
            print(f"    {label:10s}: {n:4d}", flush=True)
        print(
            f"\n  [reference] Exact selection thresholds (20-100, ADV >= $2M): "
            f"{int(((df.recent_close >= 20) & (df.recent_close <= 100) & (df.adv20_dollar >= 2_000_000)).sum())}",
            flush=True,
        )

    if dry_run:
        print("\n  [dry-run] No file written.", flush=True)
    else:
        OUTPUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        out_cols = [
            "ticker", "recent_close", "adv20_dollar",
            "adv20_sessions_available", "last_parquet_date", "built_date",
        ]
        op[out_cols].to_csv(OUTPUT_CSV, index=False)
        print(f"\n  [OK] Written: {OUTPUT_CSV}", flush=True)
        print(f"       Rows: {len(op)}", flush=True)

    return op


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Build the module-specific operational universe for "
            "gap_directional_trap__candidate_1_v1. "
            "Reads existing daily parquets only — no API calls."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts only. Do not write the output CSV.",
    )
    parser.add_argument(
        "--no-filter",
        action="store_true",
        help=(
            "Disable the pre-filter and include all US CS tickers with parquets. "
            "Useful for debugging or generating a reference comparison."
        ),
    )
    args = parser.parse_args()
    build_operational_universe(dry_run=args.dry_run, no_filter=args.no_filter)


if __name__ == "__main__":
    main()
