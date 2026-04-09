"""
engineering_source_code/production_utilities/engineering_google_sheets_push.py

Pushes the canonical trade journal mirror to Google Sheets.

Reads from:
    engineering_trade_journal/canonical_trade_journal_v1.csv

Writes to:
    Google Sheets — tabs GDT_v2 and FBR_t002

Column mapping is identical to engineering_sheet_mirror_adapter.py (V1 frozen).
Each run overwrites the full tab content: header + all matching rows.
Empty tab (no rows for that variant) writes header only.

Required environment variables:
    GOOGLE_SERVICE_ACCOUNT_JSON   Full JSON content of the service account key
    GOOGLE_SHEET_ID               Google Sheets spreadsheet ID

Behavior when secrets are missing:
    Prints a clear skip message and exits 0 (does NOT fail the pipeline).

Usage:
    # Live push (env vars required)
    python engineering_google_sheets_push.py

    # Dry run — print row counts, no API calls
    python engineering_google_sheets_push.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
ENG_ROOT       = Path(__file__).resolve().parents[2]
CANONICAL_FILE = ENG_ROOT / "engineering_trade_journal" / "canonical_trade_journal_v1.csv"

# ── Sheet column mapping (V1 frozen — mirrors engineering_sheet_mirror_adapter) ──
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

SHEET_HEADERS  = [col    for col,   _ in SHEET_COLUMNS]
JOURNAL_FIELDS = [field  for _,  field in SHEET_COLUMNS]

# Maps variant_short → Google Sheet worksheet name
TAB_MAP: dict[str, str] = {
    "gdt_v2":   "GDT_v2",
    "fbr_t002": "FBR_t002",
}


# ── Formatters ────────────────────────────────────────────────────────────────

def _fmt_risk_pct(val: str) -> str:
    try:
        return f"{float(val) * 100:.1f}%"
    except (ValueError, TypeError):
        return val


# ── Row builder ───────────────────────────────────────────────────────────────

def build_tab_rows(df: pd.DataFrame, variant_short: str) -> list[list[str]]:
    """Return [header_row, data_row, ...] for one worksheet tab."""
    rows: list[list[str]] = [SHEET_HEADERS]

    tab_df = df[df["variant_short"] == variant_short]
    for _, row in tab_df.iterrows():
        out_row: list[str] = []
        for _, journal_field in SHEET_COLUMNS:
            raw = row.get(journal_field, "")
            val = str(raw).strip() if str(raw).strip() not in ("", "nan", "None", "NaN") else ""
            if journal_field == "risk_pct" and val:
                val = _fmt_risk_pct(val)
            out_row.append(val)
        rows.append(out_row)

    return rows


# ── Main push logic ───────────────────────────────────────────────────────────

def push(dry_run: bool = False) -> None:
    # ── Check secrets ─────────────────────────────────────────────────────────
    sa_json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    sheet_id    = os.environ.get("GOOGLE_SHEET_ID", "").strip()

    if not sa_json_str:
        print("[sheets_push] GOOGLE_SERVICE_ACCOUNT_JSON not set — skipping Sheets push.")
        return
    if not sheet_id:
        print("[sheets_push] GOOGLE_SHEET_ID not set — skipping Sheets push.")
        return

    # ── Load canonical journal ────────────────────────────────────────────────
    if not CANONICAL_FILE.exists():
        print(f"[sheets_push] Canonical journal not found: {CANONICAL_FILE}")
        sys.exit(1)

    df = pd.read_csv(CANONICAL_FILE, dtype=str).fillna("")
    print(f"[sheets_push] Loaded {len(df)} row(s) from canonical journal.")

    # ── Dry run ───────────────────────────────────────────────────────────────
    if dry_run:
        for variant_short, tab_name in TAB_MAP.items():
            rows = build_tab_rows(df, variant_short)
            print(f"[sheets_push] DRY RUN: {tab_name} — {len(rows) - 1} data row(s) + header")
        print("[sheets_push] Dry run complete. No API calls made.")
        return

    # ── Import gspread (runtime — not required for dry-run) ───────────────────
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print("[sheets_push] ERROR: gspread or google-auth not installed.")
        print("[sheets_push]        Run: pip install gspread google-auth")
        sys.exit(1)

    # ── Parse service account JSON ────────────────────────────────────────────
    try:
        sa_info = json.loads(sa_json_str)
    except json.JSONDecodeError as exc:
        print(f"[sheets_push] ERROR: GOOGLE_SERVICE_ACCOUNT_JSON is not valid JSON: {exc}")
        sys.exit(1)

    # ── Authenticate ──────────────────────────────────────────────────────────
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds  = Credentials.from_service_account_info(sa_info, scopes=scopes)
    gc     = gspread.authorize(creds)

    # ── Open spreadsheet ──────────────────────────────────────────────────────
    try:
        sh = gc.open_by_key(sheet_id)
    except Exception as exc:
        print(f"[sheets_push] ERROR: Could not open sheet ID '{sheet_id}': {exc}")
        sys.exit(1)

    # ── Push each tab ─────────────────────────────────────────────────────────
    for variant_short, tab_name in TAB_MAP.items():
        rows       = build_tab_rows(df, variant_short)
        data_count = len(rows) - 1  # header not counted

        try:
            ws = sh.worksheet(tab_name)
        except gspread.exceptions.WorksheetNotFound:
            print(f"[sheets_push] ERROR: Worksheet '{tab_name}' not found in spreadsheet.")
            print( "[sheets_push]        Create the tab manually, then re-run.")
            sys.exit(1)

        ws.clear()
        ws.update("A1", rows)
        print(f"[sheets_push] {tab_name}: {data_count} data row(s) written.")

    print("[sheets_push] Google Sheets push complete.")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Push canonical trade journal mirror to Google Sheets."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print row counts without making any API calls.",
    )
    args = parser.parse_args()
    push(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
