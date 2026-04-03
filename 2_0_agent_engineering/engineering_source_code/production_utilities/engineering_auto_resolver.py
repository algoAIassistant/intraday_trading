"""
engineering_auto_resolver.py

Automatic post-session outcome resolver for canonical V1 trade journal.

Reads unresolved rows where trade_date <= today (ET), fetches 1-minute intraday
bars for each ticker via Massive API, and resolves outcomes automatically:

  not_triggered  -- price never reached entry_price in [activate_at, cancel_by) window
  stop           -- stop_price was hit before target and before flatten_by time
  target         -- target_price was hit before stop (gdt_v2 only; fbr_t002 has no target)
  time_exit      -- position still open at flatten_by_et; exit = open of flatten bar

Ambiguity rule: if stop and target are both hit within the same 1-minute bar,
default to stop (conservative) and record the ambiguity in resolver_note.

Intraday bars are cached locally per ticker/trade_date to avoid redundant API
calls on re-run:
  .../trade_journal/resolution_intraday_cache/{YYYY-MM-DD}/{ticker}.parquet

Rows that cannot be auto-resolved (data gaps, parse errors) are left unresolved
and printed as manual review items.

Spec: engineering_documents/engineering_spec__trade_journal_v1_1__auto_resolver.md

Usage:
  # Resolve all eligible unresolved rows (trade_date <= today ET)
  python engineering_auto_resolver.py

  # Resolve only rows for a specific trade_date
  python engineering_auto_resolver.py --trade-date 2026-04-02

  # Dry run: show decisions without writing to journal
  python engineering_auto_resolver.py --dry-run

  # Use local intraday cache only; skip API fetch (fails on cache miss)
  python engineering_auto_resolver.py --no-fetch

Scheduling:
  Stage 5 of the nightly orchestrators, after Telegram delivery.
  By pipeline run time (~21:00-23:00 ET), all intraday bars for the trade_date
  are available from the Massive API.

Required environment variable:
  MASSIVE_API_KEY (already required by Stage 0 of the nightly pipeline)
"""

import argparse
import re
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ENG_ROOT  = Path(__file__).resolve().parents[2]   # 2_0_agent_engineering/
REPO_ROOT = ENG_ROOT.parent                        # ai_trading_assistant/

PROVIDER_DIR = (
    REPO_ROOT
    / "1_0_strategy_research"
    / "research_source_code"
    / "data_providers"
)

# Per-run artifact outputs (gitignored — ephemeral)
JOURNAL_DIR        = ENG_ROOT / "engineering_runtime_outputs" / "plan_next_day_day_trade" / "trade_journal"
INTRADAY_CACHE_DIR = JOURNAL_DIR / "resolution_intraday_cache"

# Canonical journal — repo-persistent source of truth (git-tracked)
CANONICAL_DIR  = ENG_ROOT / "engineering_trade_journal"
CANONICAL_FILE = CANONICAL_DIR / "canonical_trade_journal_v1.csv"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ET = ZoneInfo("America/New_York")

RATE_LIMIT_SLEEP  = 0.25   # seconds between ticker fetches
MAX_429_RETRIES   = 3
BACKOFF_BASE_SECS = 60     # doubles each retry: 60s, 120s, 240s

# Windows reserved filename guard (matches existing repo pattern)
_WIN_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
    "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _today_et() -> date:
    return datetime.now(ET).date()


def _safe_cache_path(ticker: str, cache_dir: Path) -> Path:
    stem = f"{ticker}__reserved" if ticker.upper() in _WIN_RESERVED else ticker
    return cache_dir / f"{stem}.parquet"


def _is_rate_limit_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "too many" in msg or "rate limit" in msg


def _extract_retry_after(exc: Exception) -> int | None:
    m = re.search(r"retry-after[:\s]+(\d+)", str(exc), re.IGNORECASE)
    return int(m.group(1)) if m else None


def _parse_hhmm(time_str: str) -> tuple[int, int]:
    """Parse 'HH:MM' string to (hour, minute)."""
    parts = time_str.strip().split(":")
    return int(parts[0]), int(parts[1])


# ---------------------------------------------------------------------------
# Intraday bar fetch (with local cache)
# ---------------------------------------------------------------------------

def _load_provider():
    """Import fetch_intraday_1m and _get_api_key from the research provider layer."""
    sys.path.insert(0, str(PROVIDER_DIR))
    from research_provider_intraday_1m_massive import (  # noqa: E402
        fetch_intraday_1m,
        _get_api_key,
    )
    return fetch_intraday_1m, _get_api_key


def fetch_and_cache_intraday_bars(
    ticker: str,
    trade_date: date,
    fetch_intraday_1m,
    client,
) -> pd.DataFrame | None:
    """
    Return 1-minute OHLCV bars for ticker on trade_date (DatetimeIndex in
    America/New_York).  Reads from local cache when available; otherwise fetches
    via Massive API and writes to cache.

    bars: DatetimeIndex in America/New_York, columns [open, high, low, close, volume]
    """
    cache_dir  = INTRADAY_CACHE_DIR / str(trade_date)
    cache_file = _safe_cache_path(ticker, cache_dir)

    if cache_file.exists():
        return pd.read_parquet(cache_file)

    bars = fetch_intraday_1m(ticker, trade_date, trade_date, client=client)

    if bars is not None and not bars.empty:
        cache_dir.mkdir(parents=True, exist_ok=True)
        bars.to_parquet(cache_file)

    time.sleep(RATE_LIMIT_SLEEP)
    return bars


# ---------------------------------------------------------------------------
# Resolution logic
# ---------------------------------------------------------------------------

def resolve_row(row: pd.Series, bars: pd.DataFrame) -> dict:
    """
    Apply resolution logic to one unresolved journal row using 1-minute bars.

    bars: DataFrame with DatetimeIndex in America/New_York and columns
          [open, high, low, close, volume], sorted ascending.

    Returns a dict with keys:
      resolved_status, exit_price, realized_r, resolver_note

    Or a dict with key _flag (str) if the row cannot be auto-resolved.
    """
    # ── Parse required fields ─────────────────────────────────────────────────
    try:
        entry_price = float(row["entry_price"])
        stop_price  = float(row["stop_price"])
        risk_dollar = float(row["risk_dollar"])
    except (ValueError, TypeError) as exc:
        return {"_flag": f"parse_error_prices: {exc}"}

    if risk_dollar == 0.0:
        return {"_flag": "risk_dollar_is_zero"}

    target_raw  = str(row.get("target_price", "")).strip()
    has_target  = bool(target_raw and target_raw.lower() not in ("nan", ""))
    target_price = float(target_raw) if has_target else None

    activate_str = (str(row.get("activate_at_et", "")).strip() or "13:15")
    cancel_str   = (str(row.get("cancel_by_et",  "")).strip() or "13:30")
    flatten_str  = (str(row.get("flatten_by_et", "")).strip() or "14:30")

    act_h,  act_m  = _parse_hhmm(activate_str)
    can_h,  can_m  = _parse_hhmm(cancel_str)
    flat_h, flat_m = _parse_hhmm(flatten_str)

    # ── Pre-compute index hour/minute from NY-aware DatetimeIndex ─────────────
    idx    = bars.index
    hour   = idx.hour
    minute = idx.minute

    # ── Step 1: trigger window  [activate_at, cancel_by) ─────────────────────
    trigger_mask = (
        ((hour > act_h) | ((hour == act_h) & (minute >= act_m))) &
        ((hour < can_h) | ((hour == can_h) & (minute < can_m)))
    )
    trigger_bars = bars[trigger_mask]

    if len(trigger_bars) == 0:
        return {"_flag": f"no_bars_in_trigger_window ({activate_str}-{cancel_str} ET)"}

    triggered_mask = trigger_bars["high"] >= entry_price

    if not triggered_mask.any():
        return {
            "resolved_status": "not_triggered",
            "exit_price":      None,
            "realized_r":      "0.0",
            "resolver_note":   (
                f"high never reached entry={entry_price:.4f} "
                f"in {activate_str}-{cancel_str} ET window"
            ),
        }

    # ── Step 2: entry triggered — first bar where high >= entry_price ─────────
    entry_bar_ts = trigger_bars[triggered_mask].index[0]

    # ── Step 3: post-entry scan  [entry_bar_ts, flatten_by] ──────────────────
    # Include the entry bar itself (same-bar stop/target scenario after entry fill)
    post_mask = (
        (bars.index >= entry_bar_ts) &
        ((hour < flat_h) | ((hour == flat_h) & (minute <= flat_m)))
    )
    post_bars = bars[post_mask]

    if len(post_bars) == 0:
        return {"_flag": "no_post_entry_bars"}

    stop_hit_ts   = None
    target_hit_ts = None

    for ts, bar in post_bars.iterrows():
        if stop_hit_ts is None and bar["low"] <= stop_price:
            stop_hit_ts = ts
        if target_hit_ts is None and has_target and bar["high"] >= target_price:
            target_hit_ts = ts
        # Early exit once both found (or stop found and no target)
        if stop_hit_ts is not None and (target_hit_ts is not None or not has_target):
            break

    # ── Step 4: classify exit ─────────────────────────────────────────────────
    if stop_hit_ts is not None and target_hit_ts is not None:
        if stop_hit_ts < target_hit_ts:
            r = round((stop_price - entry_price) / risk_dollar, 4)
            return {
                "resolved_status": "stop",
                "exit_price":      str(stop_price),
                "realized_r":      str(r),
                "resolver_note":   "",
            }
        elif target_hit_ts < stop_hit_ts:
            r = round((target_price - entry_price) / risk_dollar, 4)
            return {
                "resolved_status": "target",
                "exit_price":      str(target_price),
                "realized_r":      str(r),
                "resolver_note":   "",
            }
        else:
            # Same 1-minute bar -- conservative default: stop
            r = round((stop_price - entry_price) / risk_dollar, 4)
            return {
                "resolved_status": "stop",
                "exit_price":      str(stop_price),
                "realized_r":      str(r),
                "resolver_note":   (
                    f"AMBIGUOUS: stop ({stop_price}) and target ({target_price}) "
                    "both breached in same 1m bar; defaulted to stop (conservative)"
                ),
            }

    elif stop_hit_ts is not None:
        r = round((stop_price - entry_price) / risk_dollar, 4)
        return {
            "resolved_status": "stop",
            "exit_price":      str(stop_price),
            "realized_r":      str(r),
            "resolver_note":   "",
        }

    elif target_hit_ts is not None:
        r = round((target_price - entry_price) / risk_dollar, 4)
        return {
            "resolved_status": "target",
            "exit_price":      str(target_price),
            "realized_r":      str(r),
            "resolver_note":   "",
        }

    else:
        # ── Time exit: flatten at flatten_by_et ───────────────────────────────
        # Exit price = open of the bar AT flatten time (if present),
        # else close of the last bar before flatten time.
        at_flatten_mask = (hour == flat_h) & (minute == flat_m)
        at_flatten_bars = bars[at_flatten_mask]

        if len(at_flatten_bars) > 0:
            exit_price_val = round(float(at_flatten_bars.iloc[0]["open"]), 4)
            bar_ts_label   = str(at_flatten_bars.index[0])[:16]
        else:
            # Fallback: close of last bar before flatten time
            before_flatten_mask = (
                (hour < flat_h) | ((hour == flat_h) & (minute < flat_m))
            )
            before_flatten = bars[before_flatten_mask]
            if len(before_flatten) == 0:
                return {"_flag": f"no_bars_at_or_before_flatten ({flatten_str} ET)"}
            exit_price_val = round(float(before_flatten.iloc[-1]["close"]), 4)
            bar_ts_label   = str(before_flatten.index[-1])[:16]

        r = round((exit_price_val - entry_price) / risk_dollar, 4)
        return {
            "resolved_status": "time_exit",
            "exit_price":      str(exit_price_val),
            "realized_r":      str(r),
            "resolver_note":   (
                f"time_exit: exit_price=open of {bar_ts_label} ET bar "
                f"(flatten_by={flatten_str} ET)"
            ),
        }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Auto resolver V1.1 -- automatic post-session outcome resolution "
            "for canonical trade journal"
        )
    )
    parser.add_argument(
        "--trade-date",
        metavar="YYYY-MM-DD",
        default=None,
        help=(
            "Resolve only rows with this trade_date. "
            "Default: all eligible unresolved rows (trade_date <= today ET)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print resolution decisions without writing to the journal.",
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help=(
            "Use local intraday cache only; skip Massive API fetch. "
            "Rows with missing cache are skipped (not resolved)."
        ),
    )
    args = parser.parse_args()

    # ── Load canonical journal ────────────────────────────────────────────────
    if not CANONICAL_FILE.exists():
        print(f"[auto_resolver] canonical journal not found: {CANONICAL_FILE}")
        print("[auto_resolver] Run engineering_journal_writer.py first.")
        sys.exit(1)

    df = pd.read_csv(CANONICAL_FILE, dtype=str).fillna("")

    # ── Filter eligible rows ──────────────────────────────────────────────────
    today_et = _today_et()
    unresolved_mask = df["resolved_status"] == "unresolved"

    if args.trade_date:
        date_mask = df["trade_date"] == args.trade_date
    else:
        def _le_today(d_str: str) -> bool:
            try:
                return date.fromisoformat(d_str) <= today_et
            except ValueError:
                return False
        date_mask = df["trade_date"].apply(_le_today)

    eligible = df[unresolved_mask & date_mask].copy()

    if len(eligible) == 0:
        print("[auto_resolver] No eligible unresolved rows found. Nothing to do.")
        return

    print(f"\n[auto_resolver] {len(eligible)} unresolved row(s) eligible for resolution.")

    # ── Load Massive API provider (unless --no-fetch) ─────────────────────────
    client = None
    fetch_fn = None

    if not args.no_fetch:
        try:
            fetch_intraday_1m, _get_api_key = _load_provider()
        except ImportError as exc:
            print(f"[auto_resolver] ERROR: cannot import data provider: {exc}")
            sys.exit(1)

        try:
            from massive import RESTClient  # noqa: PLC0415
            client = RESTClient(api_key=_get_api_key())
        except Exception as exc:
            print(f"[auto_resolver] ERROR: cannot connect to Massive API: {exc}")
            sys.exit(1)

        fetch_fn = fetch_intraday_1m

    # ── Process rows grouped by trade_date ────────────────────────────────────
    resolved_count = 0
    flagged_rows   = []   # list of (journal_id, reason)

    for trade_date_str, group in eligible.groupby("trade_date"):
        trade_date_obj = date.fromisoformat(trade_date_str)
        print(f"\n[auto_resolver] trade_date={trade_date_str}  ({len(group)} rows)")

        for _, row in group.iterrows():
            ticker     = str(row["ticker"])
            journal_id = str(row["journal_id"])

            # ── Load or fetch intraday bars ───────────────────────────────────
            if args.no_fetch:
                cache_file = _safe_cache_path(
                    ticker, INTRADAY_CACHE_DIR / str(trade_date_obj)
                )
                if not cache_file.exists():
                    print(f"  {journal_id}: no cached bars (--no-fetch set) -- skipped")
                    flagged_rows.append((journal_id, "skipped_no_cache"))
                    continue
                bars = pd.read_parquet(cache_file)
            else:
                bars = fetch_and_cache_intraday_bars(
                    ticker, trade_date_obj, fetch_fn, client
                )

            if bars is None or bars.empty:
                print(f"  {journal_id}: intraday fetch returned no data -- manual review required")
                flagged_rows.append((journal_id, "intraday_data_missing"))
                continue

            # ── Apply resolution logic ────────────────────────────────────────
            result = resolve_row(row, bars)

            if "_flag" in result:
                flag = result["_flag"]
                print(f"  {journal_id}: MANUAL REVIEW REQUIRED  ({flag})")
                flagged_rows.append((journal_id, flag))
                continue

            status   = result["resolved_status"]
            exit_p   = result.get("exit_price")
            realized = result.get("realized_r", "")
            note     = result.get("resolver_note", "")

            ambig_tag = "  [AMBIGUOUS -- check resolver_note]" if "AMBIGUOUS" in note else ""
            print(
                f"  {journal_id}: {status:<14}  "
                f"exit={exit_p if exit_p else 'n/a':<10}  "
                f"r={realized}{ambig_tag}",
                flush=True,
            )

            if not args.dry_run:
                idx_pos = df.index[df["journal_id"] == journal_id][0]
                df.at[idx_pos, "resolved_status"]   = status
                df.at[idx_pos, "resolved_date"]     = trade_date_str
                df.at[idx_pos, "exit_reason"]       = status
                df.at[idx_pos, "actual_exit_price"] = exit_p if exit_p is not None else ""
                df.at[idx_pos, "realized_r"]        = realized
                df.at[idx_pos, "resolver_note"]     = note
                df.at[idx_pos, "updated_at"]        = _now_utc()
                resolved_count += 1

    # ── Persist journal ───────────────────────────────────────────────────────
    if not args.dry_run and resolved_count > 0:
        df.to_csv(CANONICAL_FILE, index=False)
        print(f"\n[auto_resolver] journal saved: {CANONICAL_FILE}")

    # ── Print summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}", flush=True)
    print(f"  AUTO-RESOLVER SUMMARY", flush=True)
    print(f"  eligible rows:  {len(eligible)}", flush=True)
    print(f"  resolved:       {resolved_count}", flush=True)
    print(f"  flagged:        {len(flagged_rows)}", flush=True)
    if args.dry_run:
        print(f"  mode:           DRY-RUN (no writes)", flush=True)
    print(f"{'='*60}", flush=True)

    if flagged_rows:
        print(f"\n  Rows requiring manual review:", flush=True)
        for jid, reason in flagged_rows:
            print(f"    {jid}  ({reason})", flush=True)
        print(flush=True)


if __name__ == "__main__":
    main()
