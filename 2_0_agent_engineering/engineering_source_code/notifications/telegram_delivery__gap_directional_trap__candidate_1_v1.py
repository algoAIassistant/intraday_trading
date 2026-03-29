"""
engineering_source_code/notifications/telegram_delivery__gap_directional_trap__candidate_1_v1.py

Reads the latest (or date-specified) selected_top_3 CSV for
gap_directional_trap__candidate_1_v1 and delivers a formatted Telegram digest.

Reads from:
    engineering_runtime_outputs/plan_next_day_day_trade/
        gap_directional_trap__candidate_1_v1/
        selected_top_3__gap_directional_trap__candidate_1_v1__YYYY-MM-DD.csv

Does NOT:
    - recompute scan logic
    - recompute selection/ranking logic
    - mutate any input file

Usage:
    python telegram_delivery__gap_directional_trap__candidate_1_v1.py [--signal-date YYYY-MM-DD] [--preview]

Modes:
    --preview       Print formatted message to stdout. Nothing sent.
    (default)       Send via Telegram Bot API using env vars.

Required environment variables (only for real send):
    TELEGRAM_BOT_TOKEN    Telegram bot token
    TELEGRAM_CHAT_ID      Target chat or channel ID
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
    / "gap_directional_trap__candidate_1_v1"
)

FILE_PREFIX = "selected_top_3__gap_directional_trap__candidate_1_v1__"
DATE_PATTERN = re.compile(
    r"selected_top_3__gap_directional_trap__candidate_1_v1__(\d{4}_\d{2}_\d{2})\.csv$"
)

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
VARIANT_ID = "gap_directional_trap__bearish_medium_large__candidate_1_v1"
TRACK_NAME = "plan_next_day_day_trade"

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


# ---------------------------------------------------------------------------
# File resolution
# ---------------------------------------------------------------------------

def find_latest_selected_top_3() -> Path:
    """Return path to the most recent selected_top_3 file (by date in filename)."""
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
    """Return path to selected_top_3 file for a specific date.

    Accepts both ISO format (2026-03-24) and underscore format (2026_03_24).
    Filenames on disk use underscore format per project naming rules.
    """
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

def fmt_dollar(val, decimals: int = 1) -> str:
    """Format a dollar volume value: 45553740.99 → $45.6M"""
    try:
        v = float(val)
        if v >= 1_000_000:
            return f"${v / 1_000_000:.{decimals}f}M"
        if v >= 1_000:
            return f"${v / 1_000:.{decimals}f}K"
        return f"${v:.2f}"
    except (ValueError, TypeError):
        return str(val)


def fmt_pct(val) -> str:
    """Format decimal fraction to percent string: 0.0498 → 5.0%"""
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
        return f"{float(val):.4f}"
    except (ValueError, TypeError):
        return str(val)


def fmt_price(val) -> str:
    try:
        return f"${float(val):.2f}"
    except (ValueError, TypeError):
        return str(val)


def is_blank(val) -> bool:
    """True if value is empty, nan, or None string."""
    s = str(val).strip()
    return s in ("", "nan", "None", "NaN")


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------

def build_no_signals_message(signal_date: str, trade_date: str) -> str:
    td = trade_date if trade_date and not is_blank(trade_date) else "N/A"
    lines = [
        "<b>Plan Next Day Day Trade</b>",
        f"<code>{VARIANT_ID}</code>",
        "",
        f"Signal date:  {signal_date}",
        f"Trade date:   {td}",
        "",
        "No qualified signals for this date.",
    ]
    return "\n".join(lines)


def build_digest_message(df: pd.DataFrame) -> str:
    """Build HTML-formatted digest from the selected signals dataframe."""
    row0 = df.iloc[0]
    signal_date = str(row0.get("signal_date", "")).strip()
    trade_date  = str(row0.get("trade_date", "")).strip()
    n = len(df)

    lines = [
        "<b>Plan Next Day Day Trade</b>",
        f"<code>{VARIANT_ID}</code>",
        "",
        f"Signal date:  {signal_date}",
        f"Trade date:   {trade_date}",
        f"Signals:      {n}",
    ]

    for _, row in df.iterrows():
        rank    = str(row.get("selection_rank_overall", "")).strip()
        ticker  = str(row.get("ticker", "")).strip()
        bucket  = str(row.get("price_bucket_operator", "")).strip()
        entry   = fmt_price(row.get("entry_price", ""))
        stop    = fmt_price(row.get("stop_price", ""))
        target  = fmt_price(row.get("target_price", ""))
        risk    = fmt_pct(row.get("risk_pct", ""))
        gap     = str(row.get("gap_size_band", "")).strip()
        regime  = str(row.get("market_regime_label", "")).strip()
        adv     = fmt_dollar(row.get("avg_daily_dollar_volume", ""))
        rvol    = fmt_rvol(row.get("relative_volume", ""))
        score   = fmt_score(row.get("selection_score", ""))
        exit_r  = str(row.get("same_day_exit_rule", "")).strip()
        warn    = str(row.get("warning_flags", "")).strip()
        pos     = str(row.get("position_sizing_note", "")).strip()

        lines.append("")
        lines.append(f"<b>-- #{rank}  {ticker} ------------------</b>")
        lines.append(f"Bucket:   {bucket}")
        lines.append(f"Entry:    {entry}")
        lines.append(f"Stop:     {stop}")
        lines.append(f"Target:   {target}")
        lines.append(f"Risk:     {risk}")
        lines.append(f"Gap:      {gap}")
        lines.append(f"Regime:   {regime}")
        lines.append(f"ADV:      {adv}")
        lines.append(f"RVOL:     {rvol}")
        lines.append(f"Score:    {score}")
        lines.append(f"Exit:     {exit_r}")
        if not is_blank(pos):
            lines.append(f"Size:     {pos}")
        if not is_blank(warn):
            lines.append(f"Flags:    {warn}")

    return "\n".join(lines)


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
        description=(
            "Telegram delivery for gap_directional_trap__candidate_1_v1 selected top 3."
        )
    )
    parser.add_argument(
        "--signal-date",
        metavar="YYYY-MM-DD",
        help="Use selected_top_3 file for this signal date. Defaults to latest.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Print the formatted message to stdout without sending.",
    )
    args = parser.parse_args()

    # --- resolve file ---
    if args.signal_date:
        csv_path = find_selected_top_3_for_date(args.signal_date)
    else:
        csv_path = find_latest_selected_top_3()

    print(f"Reading: {csv_path.name}", file=sys.stderr)

    df = pd.read_csv(csv_path, dtype=str)
    df_selected = df[df["selected_for_delivery"].str.strip().str.lower() == "true"].copy()

    # --- build message ---
    if df_selected.empty:
        m = DATE_PATTERN.search(csv_path.name)
        sig_date = m.group(1).replace("_", "-") if m else "unknown"
        # try to pull trade_date from any row in the full df
        trade_date = ""
        if not df.empty and "trade_date" in df.columns:
            trade_date = str(df.iloc[0]["trade_date"]).strip()
        message = build_no_signals_message(sig_date, trade_date)
    else:
        message = build_digest_message(df_selected)

    # --- preview or send ---
    if args.preview:
        print("--- PREVIEW --------------------------------------------------")
        print(message)
        print("--------------------------------------------------------------")
        print(f"\nMessage length: {len(message)} chars", file=sys.stderr)
        print("Preview mode — nothing sent.", file=sys.stderr)
        return

    token   = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

    if not token:
        print("ERROR: TELEGRAM_BOT_TOKEN env var is not set.", file=sys.stderr)
        sys.exit(1)
    if not chat_id:
        print("ERROR: TELEGRAM_CHAT_ID env var is not set.", file=sys.stderr)
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
