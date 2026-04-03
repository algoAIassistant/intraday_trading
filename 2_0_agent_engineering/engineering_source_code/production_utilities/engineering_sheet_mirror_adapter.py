"""
engineering_sheet_mirror_adapter.py

Produces a Google Sheet mirror-ready JSON payload from the canonical trade journal.
Does NOT make any Google Sheets API calls. This is a clean adapter boundary.

Output:
  engineering_runtime_outputs/plan_next_day_day_trade/trade_journal/
    sheet_mirror_payload__{YYYY_MM_DD}.json

Payload structure:
  {
    "generated_at": "...",
    "source_journal": "canonical_trade_journal_v1.csv",
    "gdt_v2_tab": [ { column: value, ... }, ... ],
    "fbr_t002_tab": [ { column: value, ... }, ... ]
  }

Visible sheet columns are defined in:
  2_0_agent_engineering/engineering_documents/engineering_spec__trade_journal_v1__sheet_mapping.md

Usage:
  # Produce payload for today
  python engineering_sheet_mirror_adapter.py

  # Produce payload for a specific date (filters to that signal_date)
  python engineering_sheet_mirror_adapter.py --signal-date 2026-03-31

  # Produce payload for all dates (full journal)
  python engineering_sheet_mirror_adapter.py --all
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────
ENG_ROOT       = Path(__file__).resolve().parents[2]
# Per-run artifact outputs (gitignored — ephemeral)
JOURNAL_DIR    = ENG_ROOT / "engineering_runtime_outputs" / "plan_next_day_day_trade" / "trade_journal"
# Canonical journal — repo-persistent source of truth (git-tracked)
CANONICAL_DIR  = ENG_ROOT / "engineering_trade_journal"
CANONICAL_FILE = CANONICAL_DIR / "canonical_trade_journal_v1.csv"

# ── Sheet column mapping (V1 frozen) ──────────────────────────────────────────
# Maps sheet column header → journal field name
SHEET_COLUMNS: list[tuple[str, str]] = [
    ("Signal Date",  "signal_date"),
    ("Trade Date",   "trade_date"),
    ("Ticker",       "ticker"),
    ("Block",        "variant_short"),
    ("Entry",        "entry_price"),
    ("Stop",         "stop_price"),
    ("Target",       "target_price"),
    ("Risk%",        "risk_pct"),
    ("Activate ET",  "activate_at_et"),
    ("Cancel ET",    "cancel_by_et"),
    ("Flatten ET",   "flatten_by_et"),
    ("Regime",       "market_regime_label"),
    ("Score",        "selection_score"),
    ("Flags",        "warning_flags"),
    ("Status",       "resolved_status"),
    ("Resolved",     "resolved_date"),
    ("Exit Reason",  "exit_reason"),
    ("Exit Price",   "actual_exit_price"),
    ("Realized R",   "realized_r"),
    ("Note",         "resolver_note"),
]

SHEET_HEADERS = [col for col, _ in SHEET_COLUMNS]
JOURNAL_FIELDS_FOR_SHEET = [field for _, field in SHEET_COLUMNS]

# Strategy block → tab name mapping
TAB_MAP = {
    "gdt_v2":   "gdt_v2_tab",
    "fbr_t002": "fbr_t002_tab",
}


def _format_risk_pct(val: str) -> str:
    """Format risk_pct as a percent string (e.g. '2.4%')."""
    try:
        return f"{float(val) * 100:.1f}%"
    except (ValueError, TypeError):
        return val


def build_sheet_row(row: pd.Series) -> dict:
    """Map a journal row to the visible sheet column format."""
    out = {}
    for sheet_col, journal_field in SHEET_COLUMNS:
        val = str(row.get(journal_field, "")) if row.get(journal_field, "") != "" else ""
        if journal_field == "risk_pct" and val:
            val = _format_risk_pct(val)
        out[sheet_col] = val
    return out


def build_payload(df: pd.DataFrame, signal_date: str | None) -> dict:
    """Build the mirror payload dict from the journal DataFrame."""
    if signal_date:
        df = df[df["signal_date"] == signal_date].copy()

    tabs: dict[str, list] = {v: [] for v in TAB_MAP.values()}

    for _, row in df.iterrows():
        variant_short = str(row.get("variant_short", "")).strip()
        tab_key       = TAB_MAP.get(variant_short)
        if tab_key is None:
            continue
        tabs[tab_key].append(build_sheet_row(row))

    return {
        "generated_at":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_journal": CANONICAL_FILE.name,
        "signal_date_filter": signal_date or "all",
        **tabs,
    }


def write_payload(payload: dict, signal_date: str | None) -> Path:
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    date_tag = (signal_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")).replace("-", "_")
    path     = JOURNAL_DIR / f"sheet_mirror_payload__{date_tag}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Produce Google Sheet mirror payload from canonical trade journal"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--signal-date",
        metavar="YYYY-MM-DD",
        default=None,
        help="Filter journal to this signal date only.",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Include all dates (full journal mirror).",
    )
    args = parser.parse_args()

    if not CANONICAL_FILE.exists():
        print(f"[sheet_mirror] canonical journal not found: {CANONICAL_FILE}")
        print("[sheet_mirror] Run engineering_journal_writer.py first.")
        sys.exit(1)

    df = pd.read_csv(CANONICAL_FILE, dtype=str).fillna("")
    print(f"[sheet_mirror] loaded journal: {len(df)} row(s)")

    signal_date = None if args.all else args.signal_date

    payload  = build_payload(df, signal_date)
    out_path = write_payload(payload, signal_date)

    gdt_count = len(payload["gdt_v2_tab"])
    fbr_count = len(payload["fbr_t002_tab"])
    print(f"[sheet_mirror] gdt_v2_tab:   {gdt_count} row(s)")
    print(f"[sheet_mirror] fbr_t002_tab: {fbr_count} row(s)")
    print(f"[sheet_mirror] payload       -> {out_path.name}")
    print()
    print("[sheet_mirror] NOTE: No API calls made. Wire gspread integration when ready.")
    print(f"[sheet_mirror]       See engineering_spec__trade_journal_v1__sheet_mapping.md")


if __name__ == "__main__":
    main()
