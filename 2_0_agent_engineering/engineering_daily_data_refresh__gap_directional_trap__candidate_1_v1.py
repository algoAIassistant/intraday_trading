"""
2_0_agent_engineering/engineering_daily_data_refresh__gap_directional_trap__candidate_1_v1.py

Stage 0 of the nightly pipeline for gap_directional_trap__candidate_1_v1.

Purpose:
  Incrementally extend the daily data caches so the nightly scan sees
  the most recent closed market day.

  Three sub-tasks (in order):
    A. Extend stock daily OHLCV parquets for the full shared universe
    B. Extend SPY and QQQ market daily parquets
    C. Rebuild the market-context model CSV (pure computation, no API)
    D. Validate that the intended signal_date is present in both the
       market context CSV and SPY parquet

  Fails loudly (non-zero exit) if the required signal_date is absent
  after refresh so the downstream scan cannot proceed on stale data.

Incremental extend behavior:
  - Reads each existing parquet to find its last date.
  - Fetches only the delta (last_date + 1 day → fetch_end).
  - Merges, deduplicates, and overwrites the parquet.
  - Tickers already at or beyond fetch_end are skipped (zero API calls).
  - Preserves one-parquet-per-ticker structure.
  - Windows-reserved filename safe (CON, NUL, etc.).

Provider reuse:
  Imports normalize_aggs and _get_api_key from the repo-native
  research_provider_intraday_1m_massive.py. Does NOT invent a
  parallel fetch framework.

Market context rebuild:
  Calls research_build_market_context_model_plan_next_day_day_trade.py
  as a subprocess. That script reads the updated SPY/QQQ parquets and
  overwrites the market context CSV. No logic is duplicated.

Usage:
  # Refresh to today, report latest available signal_date
  python engineering_daily_data_refresh__gap_directional_trap__candidate_1_v1.py

  # Refresh and validate a specific signal_date is present after refresh
  python engineering_daily_data_refresh__gap_directional_trap__candidate_1_v1.py --signal-date 2026-03-27

  # Preview mode (refresh still runs, extra verbosity)
  python engineering_daily_data_refresh__gap_directional_trap__candidate_1_v1.py --signal-date 2026-03-27 --preview

  # Force full shared universe (bypasses operational universe optimization; ~4x slower)
  python engineering_daily_data_refresh__gap_directional_trap__candidate_1_v1.py --signal-date 2026-03-27 --full-universe

Auth:
  Requires MASSIVE_API_KEY environment variable.

Dependencies:
  pip install -U massive pandas pyarrow numpy
"""

import argparse
import datetime
import re
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Repo layout
# ---------------------------------------------------------------------------
ENG_ROOT  = Path(__file__).resolve().parent   # 2_0_agent_engineering/
REPO_ROOT = ENG_ROOT.parent                   # ai_trading_assistant/

PROVIDER_DIR = (
    REPO_ROOT
    / "1_0_strategy_research"
    / "research_source_code"
    / "data_providers"
)

DAILY_CACHE_DIR = (
    REPO_ROOT / "1_0_strategy_research" / "research_data_cache" / "daily"
)

MARKET_DAILY_DIR = (
    REPO_ROOT / "1_0_strategy_research" / "research_data_cache" / "market" / "daily"
)

UNIVERSE_CSV = (
    REPO_ROOT
    / "0_1_shared_master_universe"
    / "shared_symbol_lists"
    / "shared_master_symbol_list_us_common_stocks.csv"
)

# Operational universe: module-specific pre-filtered CSV (~1,400 tickers).
# Built by Sub-task A0 before the API refresh. Used instead of the full
# shared universe (~4,700 tickers) to reduce refresh runtime by ~70%.
OP_UNIVERSE_CSV = (
    ENG_ROOT
    / "engineering_configs"
    / "engineering_operational_universe__gap_directional_trap__candidate_1_v1.csv"
)

OP_UNIVERSE_BUILDER_SCRIPT = (
    ENG_ROOT
    / "engineering_build_operational_universe__gap_directional_trap__candidate_1_v1.py"
)

CONTEXT_MODEL_SCRIPT = (
    REPO_ROOT
    / "1_0_strategy_research"
    / "research_source_code"
    / "market_baseline"
    / "research_build_market_context_model_plan_next_day_day_trade.py"
)

CONTEXT_MODEL_CSV = (
    REPO_ROOT
    / "1_0_strategy_research"
    / "research_outputs"
    / "family_lineages"
    / "plan_next_day_day_trade"
    / "phase_r1_market_context_model"
    / "market_context_model_plan_next_day_day_trade.csv"
)

MARKET_SYMBOLS = ["SPY", "QQQ"]

# ---------------------------------------------------------------------------
# Rate-limit constants  (same as research_build_daily_cache.py)
# ---------------------------------------------------------------------------
RATE_LIMIT_SLEEP  = 0.15    # seconds between successful fetches (~6-7 req/sec)
MAX_429_RETRIES   = 3
BACKOFF_BASE_SECS = 60      # first backoff 60s, then 120s, then 240s

# ---------------------------------------------------------------------------
# Provider import  (repo-native, no parallel fetch framework)
# ---------------------------------------------------------------------------
sys.path.insert(0, str(PROVIDER_DIR))
from research_provider_intraday_1m_massive import normalize_aggs, _get_api_key  # noqa: E402

# ---------------------------------------------------------------------------
# Windows-reserved filename guard  (mirrors research_build_daily_cache.py)
# ---------------------------------------------------------------------------
_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


def _safe_cache_path(ticker: str, cache_dir: Path) -> Path:
    stem = f"{ticker}__reserved" if ticker.upper() in _WIN_RESERVED else ticker
    return cache_dir / f"{stem}.parquet"


# ---------------------------------------------------------------------------
# 429 detection helpers
# ---------------------------------------------------------------------------

def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "too many" in msg or "rate limit" in msg


def _extract_retry_after(exc: Exception) -> int | None:
    m = re.search(r"retry-after[:\s]+(\d+)", str(exc), re.IGNORECASE)
    return int(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Parquet last-date helper
# ---------------------------------------------------------------------------

def _get_parquet_max_date(path: Path) -> datetime.date | None:
    """Return the latest date in a parquet file, or None if absent/empty."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    try:
        df = pd.read_parquet(path)
        if df.empty:
            return None
        idx = df.index
        if hasattr(idx, "tz") and idx.tz is not None:
            dates = idx.tz_convert("America/New_York").normalize().tz_localize(None)
        else:
            dates = pd.to_datetime(idx).normalize()
        return dates.max().date()
    except Exception as exc:
        print(f"  [warn] Could not read {path.name}: {exc}", flush=True)
        return None


# ---------------------------------------------------------------------------
# Single-ticker incremental extend
# ---------------------------------------------------------------------------

def _extend_one_ticker(
    ticker: str,
    cache_dir: Path,
    default_start: str,
    fetch_end: str,
    client,
) -> str:
    """
    Reads the existing parquet for ticker, finds its last date, fetches
    only the delta to fetch_end, merges, and overwrites.

    Returns: 'extended' | 'up_to_date' | 'no_data' | 'failed' | 'rate_limited'
    """
    path = _safe_cache_path(ticker, cache_dir)
    max_date = _get_parquet_max_date(path)

    target_end_date = datetime.date.fromisoformat(fetch_end)

    if max_date is not None and max_date >= target_end_date:
        return "up_to_date"

    delta_start = (
        (max_date + datetime.timedelta(days=1)).isoformat()
        if max_date is not None
        else default_start
    )

    for attempt in range(MAX_429_RETRIES + 1):
        try:
            aggs = list(client.list_aggs(
                ticker=ticker,
                multiplier=1,
                timespan="day",
                from_=delta_start,
                to=fetch_end,
                adjusted=True,
                limit=50000,
            ))
            new_df = normalize_aggs(aggs)

            if new_df is None or new_df.empty:
                # No new rows (holiday gap or ticker inactive in range)
                return "no_data"

            if path.exists() and path.stat().st_size > 0:
                try:
                    existing = pd.read_parquet(path)
                    combined = pd.concat([existing, new_df])
                    combined = combined[~combined.index.duplicated(keep="last")]
                    combined = combined.sort_index()
                except Exception:
                    combined = new_df
            else:
                combined = new_df

            combined.to_parquet(path)
            time.sleep(RATE_LIMIT_SLEEP)
            return "extended"

        except Exception as exc:
            if _is_rate_limit_error(exc):
                if attempt < MAX_429_RETRIES:
                    retry_after = _extract_retry_after(exc)
                    wait = (
                        retry_after
                        if retry_after is not None
                        else BACKOFF_BASE_SECS * (2 ** attempt)
                    )
                    print(
                        f"  {ticker}: 429 – waiting {wait}s "
                        f"(retry {attempt + 1}/{MAX_429_RETRIES}) ...",
                        flush=True,
                    )
                    time.sleep(wait)
                else:
                    print(f"  {ticker}: 429 all retries exhausted", flush=True)
                    return "rate_limited"
            else:
                print(f"  {ticker}: ERROR – {exc}", flush=True)
                return "failed"

    return "rate_limited"   # unreachable but satisfies type checker


# ---------------------------------------------------------------------------
# Sub-task A0: rebuild operational universe (pure parquet reads, no API)
# ---------------------------------------------------------------------------

def rebuild_operational_universe(full_universe: bool) -> None:
    """
    Calls the operational universe builder as a subprocess to rebuild
    engineering_configs/engineering_operational_universe__...csv from
    existing daily parquets before the API-based refresh in Sub-task A.

    Skipped (with a note) when --full-universe is active.
    """
    print(f"\n{'='*66}", flush=True)
    print("  Sub-task A0: Rebuild operational universe", flush=True)
    if full_universe:
        print("  --full-universe set. Skipping A0 (operational universe not used).", flush=True)
        print(f"{'='*66}", flush=True)
        return

    print(f"  Script : {OP_UNIVERSE_BUILDER_SCRIPT.name}", flush=True)
    print(f"  Output : {OP_UNIVERSE_CSV.name}", flush=True)
    print(f"{'='*66}", flush=True)

    if not OP_UNIVERSE_BUILDER_SCRIPT.exists():
        print(
            f"  [warn] Builder script not found: {OP_UNIVERSE_BUILDER_SCRIPT}\n"
            "  [warn] Falling back to full shared universe for Sub-task A.",
            flush=True,
        )
        return

    result = subprocess.run([sys.executable, str(OP_UNIVERSE_BUILDER_SCRIPT)])
    if result.returncode != 0:
        print(
            f"  [warn] Operational universe builder exited with code {result.returncode}.\n"
            "  [warn] Falling back to full shared universe for Sub-task A.",
            flush=True,
        )
    else:
        print("  Sub-task A0 done.", flush=True)


# ---------------------------------------------------------------------------
# Sub-task A: stock universe daily cache
# ---------------------------------------------------------------------------

def refresh_stock_daily_cache(fetch_end: str, client, full_universe: bool = False) -> dict:
    print(f"\n{'='*66}")
    if full_universe or not OP_UNIVERSE_CSV.exists():
        universe_path = UNIVERSE_CSV
        universe_label = "full shared universe"
    else:
        universe_path = OP_UNIVERSE_CSV
        universe_label = "operational universe"

    print(f"  Sub-task A: Stock daily cache — incremental extend")
    print(f"  Universe : {universe_path.name}  [{universe_label}]")
    print(f"  Cache dir: {DAILY_CACHE_DIR}")
    print(f"  Fetch end: {fetch_end}")
    print(f"{'='*66}")

    if not universe_path.exists():
        print(f"[FAIL] Universe CSV not found: {universe_path}")
        sys.exit(1)

    tickers = (
        pd.read_csv(universe_path)["ticker"]
        .dropna()
        .str.strip()
        .str.upper()
        .tolist()
    )
    print(f"  Tickers: {len(tickers)}", flush=True)

    default_start = "2021-03-25"
    counts = {"extended": 0, "up_to_date": 0, "no_data": 0, "failed": 0, "rate_limited": 0}
    problem_list: list[str] = []

    for i, ticker in enumerate(tickers, 1):
        status = _extend_one_ticker(ticker, DAILY_CACHE_DIR, default_start, fetch_end, client)
        counts[status] = counts.get(status, 0) + 1
        if status in ("failed", "rate_limited"):
            problem_list.append(ticker)

        if i % 200 == 0 or i == len(tickers):
            print(
                f"  [{i:>5}/{len(tickers)}]  "
                f"extended={counts['extended']}  "
                f"up_to_date={counts['up_to_date']}  "
                f"no_data={counts['no_data']}  "
                f"failed={counts['failed']}  "
                f"rate_limited={counts['rate_limited']}",
                flush=True,
            )

    print(f"\n  Sub-task A done — {counts}", flush=True)
    if problem_list:
        shown = problem_list[:20]
        tail  = f" ... +{len(problem_list)-20} more" if len(problem_list) > 20 else ""
        print(f"  Problems ({len(problem_list)}): {shown}{tail}", flush=True)
    return counts


# ---------------------------------------------------------------------------
# Sub-task B: market reference cache (SPY + QQQ)
# ---------------------------------------------------------------------------

def refresh_market_daily_cache(fetch_end: str, client) -> None:
    print(f"\n{'='*66}")
    print("  Sub-task B: Market daily cache — incremental extend (SPY + QQQ)")
    print(f"  Cache dir: {MARKET_DAILY_DIR}")
    print(f"  Fetch end: {fetch_end}")
    print(f"{'='*66}")

    default_start = "2021-03-25"

    for ticker in MARKET_SYMBOLS:
        status = _extend_one_ticker(
            ticker, MARKET_DAILY_DIR, default_start, fetch_end, client
        )
        print(f"  {ticker}: {status}", flush=True)

    print("  Sub-task B done.", flush=True)


# ---------------------------------------------------------------------------
# Sub-task C: rebuild market context model
# ---------------------------------------------------------------------------

def rebuild_market_context_model() -> None:
    print(f"\n{'='*66}")
    print("  Sub-task C: Rebuild market context model")
    print(f"  Script : {CONTEXT_MODEL_SCRIPT.name}")
    print(f"  Output : {CONTEXT_MODEL_CSV.name}")
    print(f"{'='*66}")

    if not CONTEXT_MODEL_SCRIPT.exists():
        print(f"[FAIL] Market context script not found: {CONTEXT_MODEL_SCRIPT}")
        sys.exit(1)

    result = subprocess.run(
        [sys.executable, str(CONTEXT_MODEL_SCRIPT)]
    )
    if result.returncode != 0:
        print(
            f"[FAIL] Market context rebuild exited with code {result.returncode}.",
            flush=True,
        )
        sys.exit(result.returncode)
    print("  Sub-task C done.", flush=True)


# ---------------------------------------------------------------------------
# Sub-task D: validate signal_date coverage
# ---------------------------------------------------------------------------

def validate_signal_date(signal_date: str | None) -> str:
    """
    Confirms that the requested signal_date (or latest available date)
    is present in both the market context CSV and the SPY parquet.

    Returns the confirmed signal_date string (YYYY-MM-DD).
    Exits non-zero if the required date is absent.
    """
    print(f"\n{'='*66}")
    print("  Sub-task D: Validate signal_date coverage")
    print(f"{'='*66}")

    if not CONTEXT_MODEL_CSV.exists():
        print(f"[FAIL] Market context CSV not found: {CONTEXT_MODEL_CSV}")
        sys.exit(1)

    ctx = pd.read_csv(CONTEXT_MODEL_CSV)
    if "date" not in ctx.columns:
        print("[FAIL] 'date' column missing from market context CSV.")
        sys.exit(1)

    all_ctx_dates = sorted(ctx["date"].dropna().unique())
    if not all_ctx_dates:
        print("[FAIL] Market context CSV contains no dates.")
        sys.exit(1)

    # Usable = rows with a real regime label (exclude warmup warmup_na)
    if "market_regime_label" in ctx.columns:
        usable_ctx = ctx[ctx["market_regime_label"] != "warmup_na"]
    else:
        usable_ctx = ctx
    usable_ctx_dates = sorted(usable_ctx["date"].dropna().unique())

    latest_ctx_date = usable_ctx_dates[-1] if usable_ctx_dates else all_ctx_dates[-1]

    # SPY parquet max date
    spy_path = MARKET_DAILY_DIR / "SPY.parquet"
    spy_max  = _get_parquet_max_date(spy_path)
    spy_max_str = spy_max.isoformat() if spy_max else "UNKNOWN"

    print(f"  Market context latest usable date : {latest_ctx_date}", flush=True)
    print(f"  SPY parquet latest date           : {spy_max_str}", flush=True)

    if signal_date is not None:
        missing = []
        if signal_date not in all_ctx_dates:
            missing.append("market_context_csv")
        if spy_max is None or spy_max.isoformat() < signal_date:
            missing.append("SPY_parquet")

        if missing:
            print(
                f"\n[FAIL] signal_date {signal_date} not found in: {missing}",
                flush=True,
            )
            print(
                f"       Latest available: context={latest_ctx_date}  SPY={spy_max_str}",
                flush=True,
            )
            print(
                "       The date may be a non-trading day, or data was not fetched.",
                flush=True,
            )
            sys.exit(1)

        print(f"\n[OK]   signal_date {signal_date} confirmed.", flush=True)
        return signal_date

    else:
        print(f"\n[OK]   Latest available signal_date: {latest_ctx_date}", flush=True)
        return latest_ctx_date


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Stage 0: daily data refresh for gap_directional_trap__candidate_1_v1. "
            "Extends stock + market parquets and rebuilds the market context model."
        )
    )
    parser.add_argument(
        "--signal-date",
        metavar="YYYY-MM-DD",
        default=None,
        help=(
            "Target signal date. After refresh, validates this date is present "
            "in both the market context CSV and SPY parquet. "
            "If omitted, refreshes to today and reports the latest available date."
        ),
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Print extra diagnostic info. Refresh still runs.",
    )
    parser.add_argument(
        "--full-universe",
        action="store_true",
        help=(
            "Use the full shared master universe (~4,700 tickers) for Sub-task A "
            "instead of the module-specific operational universe (~1,400 tickers). "
            "Also skips Sub-task A0 (operational universe rebuild). "
            "Use for debugging, validation, or when the operational universe is suspect."
        ),
    )
    args = parser.parse_args()

    # Fetch end: use signal_date if given, otherwise today
    fetch_end = args.signal_date or datetime.date.today().isoformat()

    print("\n" + "#" * 66, flush=True)
    print("  Stage 0 — daily_data_refresh", flush=True)
    print("  gap_directional_trap__candidate_1_v1", flush=True)
    print(f"  fetch_end    : {fetch_end}", flush=True)
    if args.signal_date:
        print(f"  signal_date  : {args.signal_date}  (validation target)", flush=True)
    else:
        print("  signal_date  : auto-detect (latest usable after refresh)", flush=True)
    if args.preview:
        print("  mode         : PREVIEW", flush=True)
    if args.full_universe:
        print("  flag         : --full-universe (full shared universe for Sub-task A)", flush=True)
    print("#" * 66, flush=True)

    from massive import RESTClient
    client = RESTClient(api_key=_get_api_key())

    # A0 — rebuild operational universe (pure parquet reads, no API)
    rebuild_operational_universe(full_universe=args.full_universe)

    # A — stocks
    refresh_stock_daily_cache(fetch_end, client, full_universe=args.full_universe)

    # B — market reference
    refresh_market_daily_cache(fetch_end, client)

    # C — context model (pure computation, no API)
    rebuild_market_context_model()

    # D — validate
    confirmed_date = validate_signal_date(args.signal_date)

    print(f"\n[done]  Stage 0 complete. Signal_date confirmed: {confirmed_date}\n", flush=True)


if __name__ == "__main__":
    main()
