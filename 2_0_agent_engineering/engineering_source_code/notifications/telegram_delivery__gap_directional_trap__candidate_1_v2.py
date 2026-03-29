"""
engineering_source_code/notifications/telegram_delivery__gap_directional_trap__candidate_1_v2.py

Reads the latest (or date-specified) selected_top_3 CSV for
gap_directional_trap__candidate_1_v2 and delivers a polished Telegram message
designed for easy reading on a phone.

Reads from:
    engineering_runtime_outputs/plan_next_day_day_trade/
        gap_directional_trap__candidate_1_v2/
        selected_top_3__gap_directional_trap__candidate_1_v2__YYYY_MM_DD.csv

Does NOT:
    - recompute scan logic
    - recompute selection/ranking logic
    - mutate any input file

Usage:
    python telegram_delivery__gap_directional_trap__candidate_1_v2.py [--signal-date YYYY-MM-DD] [--preview]

Modes:
    --preview       Print formatted message to stdout. Nothing sent.
    (default)       Send via Telegram Bot API using env vars.

Required environment variables (only for real send):
    TELEGRAM_BOT_TOKEN    Telegram bot token
    TELEGRAM_CHAT_ID      Target chat or channel ID

Sample rendered output (preview):

  ─────────────────────────────────────────────
  Plan Next Day Day Trade
  gap_directional_trap · bearish regime

  Signal: 2026-03-27 (Fri)
  Trade:  2026-03-28 (Mon)

  ⏰ Activate:    13:15 ET
  ⏹ Cancel if:   not triggered by 13:30 ET
  🚪 Flatten by:  14:30 ET

  2 signals ▼
  ─────────────────────────────────────────────
  #1 · MSFT · $50–70
  ─────────────────────────────────────────────
  ▶ Entry:   $62.50   (buy stop)
  ◼ Stop:    $58.33
  ✅ Target: $70.84   (2R)
     Risk:   6.7%  ·  $4.17/sh

  ADV $245M  ·  RVOL 1.52x  ·  Score 0.714
  ─────────────────────────────────────────────
  #2 · AAPL · $30–50
  ─────────────────────────────────────────────
  ▶ Entry:   $42.10
  ◼ Stop:    $39.23
  ✅ Target: $47.84   (2R)
     Risk:   6.8%  ·  $2.87/sh

  ADV $85M  ·  RVOL 1.23x  ·  Score 0.654
  ─────────────────────────────────────────────
"""

import argparse
import os
import re
import sys
from pathlib import Path

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[3]

SIGNAL_PACK_DIR = (
    REPO_ROOT
    / "2_0_agent_engineering"
    / "engineering_runtime_outputs"
    / "plan_next_day_day_trade"
    / "gap_directional_trap__candidate_1_v2"
)

FILE_PREFIX   = "selected_top_3__gap_directional_trap__candidate_1_v2__"
DATE_PATTERN  = re.compile(
    r"selected_top_3__gap_directional_trap__candidate_1_v2__(\d{4}_\d{2}_\d{2})\.csv$"
)

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
VARIANT_ID = "gap_directional_trap__bearish_medium_large__candidate_1_v2"

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

# v2 execution time fields (used in no-signal messages when the CSV is empty)
DEFAULT_ACTIVATE_ET  = "13:15"
DEFAULT_CANCEL_ET    = "13:30"
DEFAULT_EXIT_ET      = "14:30"


# ---------------------------------------------------------------------------
# File resolution
# ---------------------------------------------------------------------------

def find_latest_selected_top_3() -> Path:
    candidates = []
    for p in SIGNAL_PACK_DIR.glob(f"{FILE_PREFIX}*.csv"):
        m = DATE_PATTERN.search(p.name)
        if m:
            candidates.append((m.group(1), p))
    if not candidates:
        raise FileNotFoundError(
            f"No selected_top_3 files found in:\n  {SIGNAL_PACK_DIR}"
        )
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def find_selected_top_3_for_date(signal_date: str) -> Path:
    date_str = signal_date.replace("-", "_")
    target = SIGNAL_PACK_DIR / f"{FILE_PREFIX}{date_str}.csv"
    if not target.exists():
        raise FileNotFoundError(
            f"No selected_top_3 file for date {signal_date}:\n  {target}"
        )
    return target


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def fmt_dollar_vol(val) -> str:
    """$45.6M / $2.3M style."""
    try:
        v = float(val)
        if v >= 1_000_000:
            return f"${v / 1_000_000:.1f}M"
        if v >= 1_000:
            return f"${v / 1_000:.1f}K"
        return f"${v:.2f}"
    except (ValueError, TypeError):
        return str(val)


def fmt_price(val) -> str:
    try:
        return f"${float(val):.2f}"
    except (ValueError, TypeError):
        return str(val)


def fmt_pct(val) -> str:
    """0.0498 → 5.0%"""
    try:
        return f"{float(val) * 100:.1f}%"
    except (ValueError, TypeError):
        return str(val)


def fmt_rvol(val) -> str:
    try:
        return f"{float(val):.2f}x"
    except (ValueError, TypeError):
        return str(val)


def fmt_score(val) -> str:
    try:
        return f"{float(val):.3f}"
    except (ValueError, TypeError):
        return str(val)


def is_blank(val) -> bool:
    return str(val).strip() in ("", "nan", "None", "NaN")


def get_str(row, key: str) -> str:
    v = row.get(key, "")
    return "" if is_blank(v) else str(v).strip()


# ---------------------------------------------------------------------------
# Date formatting helpers
# ---------------------------------------------------------------------------

_WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def fmt_date_with_day(date_str: str) -> str:
    """'2026-03-27' → '2026-03-27 (Fri)'"""
    try:
        import datetime
        d = datetime.date.fromisoformat(date_str)
        return f"{date_str} ({_WEEKDAY_NAMES[d.weekday()]})"
    except Exception:
        return date_str


def fmt_bucket_label(bucket: str) -> str:
    """'30_to_50' → '$30–50'"""
    try:
        parts = bucket.replace("_to_", "–").replace("_", "")
        return f"${parts}"
    except Exception:
        return bucket


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------

def _header_block(signal_date: str, trade_date: str, n_signals: int,
                  activate_et: str, cancel_et: str, exit_et: str) -> list[str]:
    sig_fmt   = fmt_date_with_day(signal_date) if signal_date else "N/A"
    trade_fmt = fmt_date_with_day(trade_date)  if trade_date  else "N/A"

    sig_count = f"{n_signals} signal{'s' if n_signals != 1 else ''}" if n_signals > 0 else "No signals"

    lines = [
        "<b>Plan Next Day Day Trade</b>",
        "<b>gap_directional_trap · bearish regime</b>",
        "",
        f"Signal: {sig_fmt}",
        f"Trade:  {trade_fmt}",
        "",
        f"⏰ Activate:    <b>{activate_et} ET</b>",
        f"⏹ Cancel if:   not triggered by <b>{cancel_et} ET</b>",
        f"🚪 Flatten by:  <b>{exit_et} ET</b>",
        "",
        f"{sig_count} ▼",
    ]
    return lines


def _signal_block(rank: int, row: pd.Series) -> list[str]:
    ticker    = get_str(row, "ticker")
    bucket    = fmt_bucket_label(get_str(row, "price_bucket_operator"))
    entry     = fmt_price(row.get("entry_price"))
    stop      = fmt_price(row.get("stop_price"))
    target    = fmt_price(row.get("target_price"))
    risk_pct  = fmt_pct(row.get("risk_pct"))
    risk_dol  = row.get("risk_dollar")
    adv       = fmt_dollar_vol(row.get("avg_daily_dollar_volume"))
    rvol      = fmt_rvol(row.get("relative_volume"))
    score     = fmt_score(row.get("selection_score"))
    gap_band  = get_str(row, "gap_size_band")
    warnings  = get_str(row, "warning_flags")

    try:
        risk_per_share = f"  ·  ${float(risk_dol):.2f}/sh"
    except (ValueError, TypeError):
        risk_per_share = ""

    lines = [
        "",
        f"<b>{'─'*40}</b>",
        f"<b>#{rank}  ·  {ticker}  ·  {bucket}</b>",
        f"<b>{'─'*40}</b>",
        f"▶ Entry:   <b>{entry}</b>   <i>(buy stop)</i>",
        f"◼ Stop:    {stop}",
        f"✅ Target: {target}   <i>(2R)</i>",
        f"   Risk:   {risk_pct}{risk_per_share}",
        "",
        f"ADV {adv}  ·  RVOL {rvol}  ·  Score {score}",
        f"Gap: {gap_band}",
    ]

    if warnings:
        lines.append(f"⚠️ {warnings}")

    return lines


def build_digest_message(df: pd.DataFrame) -> str:
    """Build phone-readable HTML message from selected signals dataframe."""
    row0 = df.iloc[0]

    signal_date  = get_str(row0, "signal_date")
    trade_date   = get_str(row0, "trade_date")
    activate_et  = get_str(row0, "activate_order_at_et")  or DEFAULT_ACTIVATE_ET
    cancel_et    = get_str(row0, "cancel_if_not_triggered_by_et") or DEFAULT_CANCEL_ET
    exit_et      = get_str(row0, "forced_exit_time_et")   or DEFAULT_EXIT_ET

    lines = _header_block(signal_date, trade_date, len(df), activate_et, cancel_et, exit_et)

    for rank, (_, row) in enumerate(df.iterrows(), start=1):
        lines.extend(_signal_block(rank, row))

    lines += [
        "",
        f"<b>{'─'*40}</b>",
        "<i>Wide stop (~4.7% avg risk). Size small.</i>",
        "<i>Do not adjust stops/targets intraday.</i>",
    ]

    return "\n".join(lines)


def build_no_signals_message(signal_date: str, trade_date: str,
                              regime: str = "") -> str:
    sig_fmt   = fmt_date_with_day(signal_date) if signal_date else "N/A"
    trade_fmt = fmt_date_with_day(trade_date)  if trade_date  else "N/A"

    regime_note = (
        f"\nRegime today: <b>{regime}</b>\n"
        "This variant requires <b>bearish</b> regime to generate signals."
        if regime and regime != "bearish"
        else ""
    )

    lines = [
        "<b>Plan Next Day Day Trade</b>",
        "<b>gap_directional_trap · candidate_1_v2</b>",
        "",
        f"Signal: {sig_fmt}",
        f"Trade:  {trade_fmt}",
        "",
        "No signals for this date.",
        regime_note,
    ]
    return "\n".join(l for l in lines if l is not None)


# ---------------------------------------------------------------------------
# Telegram send
# ---------------------------------------------------------------------------

def send_telegram_message(text: str, token: str, chat_id: str) -> dict:
    url = TELEGRAM_API_URL.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Telegram delivery for gap_directional_trap candidate_1_v2."
    )
    parser.add_argument(
        "--signal-date",
        metavar="YYYY-MM-DD",
        help="Use selected_top_3 for this signal date. Defaults to latest.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Print the formatted message to stdout without sending.",
    )
    args = parser.parse_args()

    # Resolve file
    if args.signal_date:
        csv_path = find_selected_top_3_for_date(args.signal_date)
    else:
        csv_path = find_latest_selected_top_3()

    print(f"Reading: {csv_path.name}", file=sys.stderr)

    df = pd.read_csv(csv_path, dtype=str)

    # Filter to selected rows only
    if "selected_for_delivery" in df.columns:
        df_selected = df[
            df["selected_for_delivery"].str.strip().str.lower() == "true"
        ].copy()
    else:
        df_selected = df.copy()

    # Build message
    if df_selected.empty:
        m = DATE_PATTERN.search(csv_path.name)
        sig_date = m.group(1).replace("_", "-") if m else "unknown"
        trade_date = ""
        regime     = ""
        if not df.empty:
            if "trade_date" in df.columns:
                trade_date = str(df.iloc[0]["trade_date"]).strip()
            if "market_regime_label" in df.columns:
                regime = str(df.iloc[0]["market_regime_label"]).strip()
        message = build_no_signals_message(sig_date, trade_date, regime)
    else:
        message = build_digest_message(df_selected)

    # Preview or send
    if args.preview:
        print("─" * 60)
        print(message)
        print("─" * 60)
        print(f"\nMessage length: {len(message)} chars", file=sys.stderr)
        print("Preview mode — nothing sent.", file=sys.stderr)
        return

    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN env var not set.", file=sys.stderr)
        sys.exit(1)
    if not chat_id:
        print("ERROR: TELEGRAM_CHAT_ID env var not set.", file=sys.stderr)
        sys.exit(1)

    result = send_telegram_message(message, token, chat_id)
    if result.get("ok"):
        msg_id = result.get("result", {}).get("message_id", "?")
        print(f"Sent. message_id={msg_id}", file=sys.stderr)
    else:
        print(f"Telegram API error: {result}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
