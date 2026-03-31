"""
engineering_source_code/notifications/telegram_delivery__failed_breakdown_reclaim__template_002.py

Reads the signal pack for failed_breakdown_reclaim__template_002 and delivers a
phone-readable Telegram message for the next-day trade plan.

Reads from:
    engineering_runtime_outputs/plan_next_day_day_trade/
        failed_breakdown_reclaim__template_002/
        signal_pack__failed_breakdown_reclaim__template_002__YYYY_MM_DD.csv

Does NOT:
    - recompute scan logic
    - recompute ADV or filter gates
    - mutate any input file

Usage:
    python telegram_delivery__failed_breakdown_reclaim__template_002.py [--signal-date YYYY-MM-DD] [--preview]

Modes:
    --preview       Print formatted message to stdout. Nothing sent.
    (default)       Send via Telegram Bot API using env vars.

Required environment variables (only for real send):
    TELEGRAM_BOT_TOKEN    Telegram bot token
    TELEGRAM_CHAT_ID      Target chat or channel ID

Sample rendered output (preview):

  ─────────────────────────────────────────────
  Plan Next Day Day Trade
  failed_breakdown_reclaim · bullish regime

  Signal: 2026-03-31 (Tue)
  Trade:  2026-04-01 (Wed)

  ⏰ Activate:    13:15 ET
  ⏹ Cancel if:   not triggered by 13:30 ET
  🚪 Flatten by:  14:30 ET
  ⚡ Target:      None (time exit only)

  3 signals ▼
  ─────────────────────────────────────────────
  #1  ·  NVDA  ·  adv_100m_plus  ·  $400–800
  ─────────────────────────────────────────────
  ▶ Entry:   $487.20   (buy stop above signal high)
  ◼ Stop:    $476.10   (signal low — no buffer)
     Risk:   2.3%  ·  $11.10/sh
     Depth:  0.82%  (breakdown below prior low)
     Reclaim: 0.12%  (close above prior low)
  ─────────────────────────────────────────────
"""

import argparse
import datetime
import os
import re
import sys
from pathlib import Path

import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
# File at: 2_0_agent_engineering/engineering_source_code/notifications/
REPO_ROOT = Path(__file__).resolve().parents[3]

SIGNAL_PACK_DIR = (
    REPO_ROOT
    / "2_0_agent_engineering"
    / "engineering_runtime_outputs"
    / "plan_next_day_day_trade"
    / "failed_breakdown_reclaim__template_002"
)

FILE_PREFIX  = "signal_pack__failed_breakdown_reclaim__template_002__"
DATE_PATTERN = re.compile(
    r"signal_pack__failed_breakdown_reclaim__template_002__(\d{4}_\d{2}_\d{2})\.csv$"
)

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
VARIANT_ID = "failed_breakdown_reclaim__weak_reclaim_depth__time_exit_primary__template_002"

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

DEFAULT_ACTIVATE_ET = "13:15"
DEFAULT_CANCEL_ET   = "13:30"
DEFAULT_EXIT_ET     = "14:30"


# ---------------------------------------------------------------------------
# File resolution
# ---------------------------------------------------------------------------

def find_latest_signal_pack() -> Path:
    candidates = []
    for p in SIGNAL_PACK_DIR.glob(f"{FILE_PREFIX}*.csv"):
        m = DATE_PATTERN.search(p.name)
        if m:
            candidates.append((m.group(1), p))
    if not candidates:
        raise FileNotFoundError(
            f"No signal_pack files found in:\n  {SIGNAL_PACK_DIR}"
        )
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def find_signal_pack_for_date(signal_date: str) -> Path:
    date_str = signal_date.replace("-", "_")
    target = SIGNAL_PACK_DIR / f"{FILE_PREFIX}{date_str}.csv"
    if not target.exists():
        raise FileNotFoundError(
            f"No signal_pack file for date {signal_date}:\n  {target}"
        )
    return target


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

_WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def fmt_date_with_day(date_str: str) -> str:
    """'2026-03-31' → '2026-03-31 (Tue)'"""
    try:
        d = datetime.date.fromisoformat(str(date_str).strip())
        return f"{date_str} ({_WEEKDAY_NAMES[d.weekday()]})"
    except Exception:
        return str(date_str)


def fmt_price(val) -> str:
    try:
        return f"${float(val):.2f}"
    except (ValueError, TypeError):
        return str(val)


def fmt_pct_raw(val) -> str:
    """0.0082 → '0.82%'"""
    try:
        return f"{float(val) * 100:.2f}%"
    except (ValueError, TypeError):
        return str(val)


def fmt_risk_pct(val) -> str:
    """0.023 → '2.3%'"""
    try:
        return f"{float(val) * 100:.1f}%"
    except (ValueError, TypeError):
        return str(val)


def fmt_price_bucket(bucket: str) -> str:
    """'price_80_200' → '$80–200'"""
    try:
        # Remove 'price_' prefix, replace _ with –
        s = bucket.replace("price_", "").replace("_", "–")
        return f"${s}"
    except Exception:
        return bucket


def is_blank(val) -> bool:
    return str(val).strip() in ("", "nan", "None", "NaN")


def get_str(row, key: str) -> str:
    v = row.get(key, "")
    return "" if is_blank(v) else str(v).strip()


# ---------------------------------------------------------------------------
# Message builders
# ---------------------------------------------------------------------------

def _header_block(signal_date: str, trade_date: str, n_signals: int,
                  regime: str, activate_et: str, cancel_et: str, exit_et: str) -> list[str]:
    sig_fmt   = fmt_date_with_day(signal_date) if signal_date else "N/A"
    trade_fmt = fmt_date_with_day(trade_date)  if trade_date  else "N/A"
    sig_count = f"{n_signals} signal{'s' if n_signals != 1 else ''}" if n_signals > 0 else "No signals"

    lines = [
        "<b>Plan Next Day Day Trade</b>",
        f"<b>failed_breakdown_reclaim · {regime} regime</b>",
        "",
        f"Signal: {sig_fmt}",
        f"Trade:  {trade_fmt}",
        "",
        f"⏰ Activate:    <b>{activate_et} ET</b>",
        f"⏹ Cancel if:   not triggered by <b>{cancel_et} ET</b>",
        f"🚪 Flatten by:  <b>{exit_et} ET</b>",
        "⚡ Target:      None  <i>(time exit only)</i>",
        "",
        f"{sig_count} ▼",
    ]
    return lines


def _signal_block(rank: int, row: pd.Series) -> list[str]:
    ticker        = get_str(row, "ticker")
    adv_bucket    = get_str(row, "adv_dollar_bucket")
    price_bucket  = fmt_price_bucket(get_str(row, "price_bucket"))
    entry         = fmt_price(row.get("entry_price"))
    stop          = fmt_price(row.get("stop_price"))
    risk_pct      = fmt_risk_pct(row.get("risk_distance_pct"))
    depth_pct     = fmt_pct_raw(row.get("breakdown_depth_pct"))
    reclaim_pct   = fmt_pct_raw(row.get("reclaim_pct"))
    ctx_conf      = get_str(row, "context_confidence")
    warnings      = get_str(row, "warning_flags")
    variant       = get_str(row, "variant_name")

    # risk per share (entry - stop)
    try:
        risk_per_share = f"  ·  ${float(row['entry_price']) - float(row['stop_price']):.2f}/sh"
    except (ValueError, TypeError, KeyError):
        risk_per_share = ""

    lines = [
        "",
        f"<b>{'─'*40}</b>",
        f"<b>#{rank}  ·  {ticker}  ·  {adv_bucket}  ·  {price_bucket}</b>",
        f"<b>{'─'*40}</b>",
        f"▶ Entry:   <b>{entry}</b>   <i>(buy stop above signal high)</i>",
        f"◼ Stop:    {stop}   <i>(signal low — no buffer)</i>",
        f"   Risk:   {risk_pct}{risk_per_share}",
        f"   Depth:  {depth_pct}  <i>(breakdown below prior low)</i>",
        f"   Reclaim: {reclaim_pct}  <i>(close above prior low)</i>",
    ]

    # Confidence line — only note if low (bearish regime)
    if ctx_conf == "low":
        lines.append(f"⚠️ conf: <b>low</b>  <i>(bearish regime — reduced edge after slippage)</i>")

    # Variant name (small)
    lines.append(f"<i>{variant}</i>")

    if warnings:
        lines.append(f"⚠️ {warnings}")

    return lines


def build_digest_message(df: pd.DataFrame) -> str:
    """Build phone-readable HTML message from signal pack dataframe."""
    row0 = df.iloc[0]

    signal_date = get_str(row0, "signal_date")
    trade_date  = get_str(row0, "trade_date")
    regime      = get_str(row0, "market_regime_label")

    lines = _header_block(
        signal_date, trade_date, len(df),
        regime,
        DEFAULT_ACTIVATE_ET, DEFAULT_CANCEL_ET, DEFAULT_EXIT_ET,
    )

    for rank, (_, row) in enumerate(df.iterrows(), start=1):
        lines.extend(_signal_block(rank, row))

    lines += [
        "",
        f"<b>{'─'*40}</b>",
        "<i>Trap setup. No fixed target — time exit only.</i>",
        "<i>Do not adjust stops intraday.</i>",
    ]

    return "\n".join(lines)


def build_no_signals_message(signal_date: str, trade_date: str, regime: str = "") -> str:
    sig_fmt   = fmt_date_with_day(signal_date) if signal_date else "N/A"
    trade_fmt = fmt_date_with_day(trade_date)  if trade_date  else "N/A"

    lines = [
        "<b>Plan Next Day Day Trade</b>",
        "<b>failed_breakdown_reclaim · template_002</b>",
        "",
        f"Signal: {sig_fmt}",
        f"Trade:  {trade_fmt}",
        "",
        "No qualifying signals for this date.",
    ]

    if regime:
        lines.append(f"Regime today: <b>{regime}</b>")
        if regime == "bearish":
            lines.append("<i>(Bearish regime — signals emit but flagged low confidence. None passed ADV/price/filter gates today.)</i>")
        else:
            lines.append("<i>(This variant runs in all regimes — no setups met the locked filters today.)</i>")

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
        description="Telegram delivery for failed_breakdown_reclaim__template_002."
    )
    parser.add_argument(
        "--signal-date",
        metavar="YYYY-MM-DD",
        help="Use signal pack for this date. Defaults to latest.",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Print the formatted message to stdout without sending.",
    )
    args = parser.parse_args()

    # Resolve file
    try:
        if args.signal_date:
            csv_path = find_signal_pack_for_date(args.signal_date)
        else:
            csv_path = find_latest_signal_pack()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Reading: {csv_path.name}", file=sys.stderr)
    df = pd.read_csv(csv_path, dtype=str)

    # Extract date/regime metadata even when df is empty
    m = DATE_PATTERN.search(csv_path.name)
    sig_date_str = m.group(1).replace("_", "-") if m else ""

    trade_date = ""
    regime     = ""
    if not df.empty:
        if "trade_date" in df.columns:
            trade_date = str(df.iloc[0]["trade_date"]).strip()
        if "market_regime_label" in df.columns:
            regime = str(df.iloc[0]["market_regime_label"]).strip()

    # Build message
    if df.empty:
        message = build_no_signals_message(sig_date_str, trade_date, regime)
    else:
        message = build_digest_message(df)

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
