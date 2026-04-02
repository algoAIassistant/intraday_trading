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

FILE_PREFIX  = "selected_top_3__failed_breakdown_reclaim__template_002__"
DATE_PATTERN = re.compile(
    r"selected_top_3__failed_breakdown_reclaim__template_002__(\d{4}_\d{2}_\d{2})\.csv$"
)

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------
VARIANT_ID = "failed_breakdown_reclaim__weak_reclaim_depth__time_exit_primary__template_002"

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"

# Telegram HTML message limit is 4096 chars. Use 4000 as safe ceiling.
TELEGRAM_MAX_CHARS = 4000

DEFAULT_ACTIVATE_ET = "13:15"
DEFAULT_CANCEL_ET   = "13:30"
DEFAULT_EXIT_ET     = "14:30"


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
    """'price_10_30' → '$10–30'"""
    try:
        s = bucket.replace("price_", "").replace("_", "–")
        return f"${s}"
    except Exception:
        return bucket


def fmt_adv_bucket(bucket: str) -> str:
    """'adv_100m_plus' → '$100M+'  |  'adv_50m_100m' → '$50–100M'"""
    mapping = {
        "adv_100m_plus": "$100M+",
        "adv_50m_100m":  "$50–100M",
        "adv_20m_50m":   "$20–50M",
    }
    return mapping.get(str(bucket).strip(), str(bucket))


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
    ticker       = get_str(row, "ticker")
    price_bucket = fmt_price_bucket(get_str(row, "price_bucket"))
    adv          = fmt_adv_bucket(get_str(row, "adv_dollar_bucket"))
    entry        = fmt_price(row.get("entry_price"))
    stop         = fmt_price(row.get("stop_price"))
    risk_pct     = fmt_risk_pct(row.get("risk_distance_pct"))
    ctx_conf     = get_str(row, "context_confidence")
    score        = fmt_score(row.get("selection_score"))
    warnings     = get_str(row, "warning_flags")

    try:
        risk_per_share = f"  ·  ${float(row['entry_price']) - float(row['stop_price']):.2f}/sh"
    except (ValueError, TypeError, KeyError):
        risk_per_share = ""

    lines = [
        "",
        f"<b>{'─'*40}</b>",
        f"<b>#{rank}  ·  {ticker}  ·  {price_bucket}</b>",
        f"<b>{'─'*40}</b>",
        f"▶ Entry:   <b>{entry}</b>   <i>(buy stop)</i>",
        f"◼ Stop:    {stop}",
        f"   Risk:   {risk_pct}{risk_per_share}",
        "",
        f"ADV {adv}  ·  conf: {ctx_conf}  ·  Score {score}",
    ]

    if ctx_conf == "low":
        lines.append("⚠️ <i>bearish regime — reduced edge after slippage</i>")

    if warnings and "very_wide_stop" in warnings:
        lines.append("⚠️ <i>wide stop — size small</i>")

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
        lines.append(f"Regime: <b>{regime}</b>  <i>(no setups met filters today)</i>")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Telegram send
# ---------------------------------------------------------------------------

def split_message_into_chunks(text: str, max_chars: int = TELEGRAM_MAX_CHARS) -> list[str]:
    """
    Split a newline-delimited HTML message into chunks each <= max_chars.

    Splits only on line boundaries so no HTML tag is ever cut mid-tag.
    Each chunk is a complete, self-contained substring of the original message.
    If a single line exceeds max_chars it is sent as its own chunk (rare edge case).
    """
    lines = text.split("\n")
    chunks: list[str] = []
    current_lines: list[str] = []
    current_len = 0

    for line in lines:
        # +1 for the \n separator that will be re-added between lines
        line_cost = len(line) + (1 if current_lines else 0)
        if current_lines and current_len + line_cost > max_chars:
            chunks.append("\n".join(current_lines))
            current_lines = [line]
            current_len = len(line)
        else:
            current_lines.append(line)
            current_len += line_cost

    if current_lines:
        chunks.append("\n".join(current_lines))

    return chunks


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


def send_telegram_chunks(chunks: list[str], token: str, chat_id: str) -> None:
    """Send a list of message chunks sequentially. Raises on first failure."""
    n = len(chunks)
    for i, chunk in enumerate(chunks, start=1):
        result = send_telegram_message(chunk, token, chat_id)
        if result.get("ok"):
            msg_id = result.get("result", {}).get("message_id", "?")
            print(f"Sent chunk {i}/{n}. message_id={msg_id}", file=sys.stderr)
        else:
            print(f"Telegram API error on chunk {i}/{n}: {result}", file=sys.stderr)
            sys.exit(1)


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
            csv_path = find_selected_top_3_for_date(args.signal_date)
        else:
            csv_path = find_latest_selected_top_3()
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

    # Build message — all rows in selected_top_3 are already selected
    if df.empty:
        message = build_no_signals_message(sig_date_str, trade_date, regime)
    else:
        message = build_digest_message(df)

    # Split into safe chunks regardless of signal count
    chunks = split_message_into_chunks(message)

    # Preview or send
    if args.preview:
        for i, chunk in enumerate(chunks, start=1):
            print("─" * 60)
            print(chunk)
            print("─" * 60)
            print(f"Chunk {i}/{len(chunks)}: {len(chunk)} chars", file=sys.stderr)
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

    send_telegram_chunks(chunks, token, chat_id)


if __name__ == "__main__":
    main()
