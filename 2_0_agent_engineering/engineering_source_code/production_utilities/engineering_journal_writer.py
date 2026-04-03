"""
engineering_journal_writer.py

Writes canonical V1 trade journal entries from nightly signal pack outputs.
Also writes a ranked snapshot of the full candidate pool for retrospective analysis.

Supported strategy blocks:
  gap_directional_trap__bearish_medium_large__candidate_1_v2         (variant_short: gdt_v2)
  failed_breakdown_reclaim__weak_reclaim_depth__time_exit_primary__template_002  (variant_short: fbr_t002)

Outputs (per run):
  trade_journal/journal_entries__{variant_short}__{YYYY_MM_DD}.csv  — this run's entries
  trade_journal/canonical_trade_journal_v1.csv                      — cumulative local journal
  trade_journal/ranked_snapshots/ranked_snapshot__{variant_short}__{YYYY_MM_DD}.csv

Idempotency:
  journal_id = {variant_short}__{YYYY_MM_DD}__{TICKER} is the primary key.
  Rows with existing journal_ids are skipped when appending to the canonical journal.

Usage:
  python engineering_journal_writer.py \\
      --strategy-block gap_directional_trap__bearish_medium_large__candidate_1_v2 \\
      --signal-date 2026-03-31

  python engineering_journal_writer.py \\
      --strategy-block failed_breakdown_reclaim__weak_reclaim_depth__time_exit_primary__template_002 \\
      --signal-date 2026-03-31

Schema spec:
  2_0_agent_engineering/engineering_documents/engineering_spec__trade_journal_v1__schema.md
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# ── Repo root resolution ───────────────────────────────────────────────────────
# File location: 2_0_agent_engineering/engineering_source_code/production_utilities/
ENG_ROOT  = Path(__file__).resolve().parents[2]   # 2_0_agent_engineering/

# ── Journal paths ──────────────────────────────────────────────────────────────
# Per-run artifact outputs (gitignored — ephemeral)
JOURNAL_DIR        = ENG_ROOT / "engineering_runtime_outputs" / "plan_next_day_day_trade" / "trade_journal"
RANKED_SNAP_DIR    = JOURNAL_DIR / "ranked_snapshots"

# Canonical journal — repo-persistent source of truth (git-tracked)
CANONICAL_DIR      = ENG_ROOT / "engineering_trade_journal"
CANONICAL_JOURNAL  = CANONICAL_DIR / "canonical_trade_journal_v1.csv"

# ── Canonical field order (V1 frozen) ─────────────────────────────────────────
JOURNAL_FIELDS = [
    "journal_id",
    "batch_id",
    "run_id",
    "strategy_block",
    "variant_short",
    "signal_date",
    "trade_date",
    "ticker",
    "entry_price",
    "stop_price",
    "target_price",
    "risk_dollar",
    "risk_pct",
    "activate_at_et",
    "cancel_by_et",
    "flatten_by_et",
    "market_regime_label",
    "gap_size_band",
    "gap_pct",
    "breakdown_depth_pct",
    "reclaim_pct",
    "close_location",
    "selection_score",
    "selection_rank_overall",
    "selection_rank_within_bucket",
    "price_bucket_operator",
    "adv_dollar",
    "adv_bucket",
    "relative_volume",
    "warning_flags",
    "resolved_status",
    "resolved_date",
    "exit_reason",
    "actual_exit_price",
    "realized_r",
    "resolver_note",
    "written_at",
    "updated_at",
]

# ── Strategy block configuration ──────────────────────────────────────────────
_STRATEGY_CONFIGS: dict[str, dict] = {
    "gap_directional_trap__bearish_medium_large__candidate_1_v2": {
        "variant_short":   "gdt_v2",
        "has_target":      True,
        "activate_at_et":  "13:15",
        "cancel_by_et":    "13:30",
        "flatten_by_et":   "14:30",
        # Source for selected signals (relative to ENG_ROOT)
        "signal_dir":      Path("engineering_runtime_outputs/plan_next_day_day_trade/gap_directional_trap__candidate_1_v2"),
        "selected_prefix": "selected_top_3__gap_directional_trap__candidate_1_v2",
        "ranked_prefix":   "ranked_signal_pack__gap_directional_trap__candidate_1_v2",
    },
    "failed_breakdown_reclaim__weak_reclaim_depth__time_exit_primary__template_002": {
        "variant_short":   "fbr_t002",
        "has_target":      False,
        "activate_at_et":  "13:15",
        "cancel_by_et":    "13:30",
        "flatten_by_et":   "14:30",
        "signal_dir":      Path("engineering_runtime_outputs/plan_next_day_day_trade/failed_breakdown_reclaim__template_002"),
        "selected_prefix": "signal_pack__failed_breakdown_reclaim__template_002",
        "ranked_prefix":   "signal_pack__failed_breakdown_reclaim__template_002",
    },
}


# ── Row mappers ───────────────────────────────────────────────────────────────

def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe(row: pd.Series, col: str, default="") -> str:
    """Return row[col] as string if present and not NaN, else default."""
    if col not in row.index:
        return default
    val = row[col]
    if pd.isna(val):
        return default
    return str(val)


def _safe_float(row: pd.Series, col: str, default="") -> str:
    if col not in row.index:
        return default
    val = row[col]
    if pd.isna(val):
        return default
    try:
        return str(float(val))
    except (TypeError, ValueError):
        return default


def map_gdt_v2_row(
    row: pd.Series,
    signal_date: str,
    run_id: str,
    variant_short: str,
    strategy_block: str,
    cfg: dict,
) -> dict:
    ticker    = str(row["ticker"]).strip().upper()
    date_tag  = signal_date.replace("-", "_")
    ts        = _now_utc()

    entry     = float(row["entry_price"])
    stop      = float(row["stop_price"])
    target    = float(row["target_price"])
    risk_d    = float(row.get("risk_dollar", entry - stop))
    risk_p    = float(row.get("risk_pct", risk_d / entry if entry > 0 else 0.0))

    activate  = _safe(row, "activate_order_at_et",          cfg["activate_at_et"])
    cancel    = _safe(row, "cancel_if_not_triggered_by_et", cfg["cancel_by_et"])
    flatten   = _safe(row, "forced_exit_time_et",           cfg["flatten_by_et"])

    return {
        "journal_id":                  f"{variant_short}__{date_tag}__{ticker}",
        "batch_id":                    f"{variant_short}__{date_tag}",
        "run_id":                      run_id,
        "strategy_block":              strategy_block,
        "variant_short":               variant_short,
        "signal_date":                 _safe(row, "signal_date", signal_date),
        "trade_date":                  _safe(row, "trade_date"),
        "ticker":                      ticker,
        "entry_price":                 str(round(entry, 4)),
        "stop_price":                  str(round(stop,  4)),
        "target_price":                str(round(target, 4)),
        "risk_dollar":                 str(round(risk_d, 4)),
        "risk_pct":                    str(round(risk_p, 6)),
        "activate_at_et":              activate,
        "cancel_by_et":                cancel,
        "flatten_by_et":               flatten,
        "market_regime_label":         _safe(row, "market_regime_label"),
        "gap_size_band":               _safe(row, "gap_size_band"),
        "gap_pct":                     _safe_float(row, "gap_pct"),
        "breakdown_depth_pct":         "",
        "reclaim_pct":                 "",
        "close_location":              _safe_float(row, "close_location"),
        "selection_score":             _safe_float(row, "selection_score"),
        "selection_rank_overall":      _safe(row, "selection_rank_overall"),
        "selection_rank_within_bucket": _safe(row, "selection_rank_within_bucket"),
        "price_bucket_operator":       _safe(row, "price_bucket_operator"),
        "adv_dollar":                  _safe_float(row, "avg_daily_dollar_volume"),
        "adv_bucket":                  "",
        "relative_volume":             _safe_float(row, "relative_volume"),
        "warning_flags":               _safe(row, "warning_flags"),
        "resolved_status":             "unresolved",
        "resolved_date":               "",
        "exit_reason":                 "",
        "actual_exit_price":           "",
        "realized_r":                  "",
        "resolver_note":               "",
        "written_at":                  ts,
        "updated_at":                  ts,
    }


def map_fbr_t002_row(
    row: pd.Series,
    signal_date: str,
    run_id: str,
    variant_short: str,
    strategy_block: str,
    cfg: dict,
) -> dict:
    ticker   = str(row["ticker"]).strip().upper()
    date_tag = signal_date.replace("-", "_")
    ts       = _now_utc()

    entry    = float(row["entry_price"])
    stop     = float(row["stop_price"])
    risk_d   = float(row.get("risk_dollar", entry - stop))
    risk_p   = risk_d / entry if entry > 0 else 0.0

    # FBR signal pack uses cancel_time_et / flatten_time_et column names
    cancel   = _safe(row, "cancel_time_et",  cfg["cancel_by_et"])
    flatten  = _safe(row, "flatten_time_et", cfg["flatten_by_et"])

    return {
        "journal_id":                  f"{variant_short}__{date_tag}__{ticker}",
        "batch_id":                    f"{variant_short}__{date_tag}",
        "run_id":                      run_id,
        "strategy_block":              strategy_block,
        "variant_short":               variant_short,
        "signal_date":                 _safe(row, "signal_date", signal_date),
        "trade_date":                  _safe(row, "trade_date"),
        "ticker":                      ticker,
        "entry_price":                 str(round(entry, 4)),
        "stop_price":                  str(round(stop,  4)),
        "target_price":                "",   # time_exit_primary — no target
        "risk_dollar":                 str(round(risk_d, 4)),
        "risk_pct":                    str(round(risk_p, 6)),
        "activate_at_et":              cfg["activate_at_et"],
        "cancel_by_et":                cancel,
        "flatten_by_et":               flatten,
        "market_regime_label":         _safe(row, "market_regime_label"),
        "gap_size_band":               "",
        "gap_pct":                     "",
        "breakdown_depth_pct":         _safe_float(row, "breakdown_depth_pct"),
        "reclaim_pct":                 _safe_float(row, "reclaim_pct"),
        "close_location":              "",
        "selection_score":             "",
        "selection_rank_overall":      "",
        "selection_rank_within_bucket": "",
        "price_bucket_operator":       _safe(row, "price_bucket"),
        "adv_dollar":                  _safe_float(row, "adv_dollar_approx"),
        "adv_bucket":                  _safe(row, "adv_dollar_bucket"),
        "relative_volume":             "",
        "warning_flags":               _safe(row, "warning_flags"),
        "resolved_status":             "unresolved",
        "resolved_date":               "",
        "exit_reason":                 "",
        "actual_exit_price":           "",
        "realized_r":                  "",
        "resolver_note":               "",
        "written_at":                  ts,
        "updated_at":                  ts,
    }


# ── Signal pack loaders ────────────────────────────────────────────────────────

def load_selected_signals(strategy_block: str, signal_date: str, cfg: dict) -> pd.DataFrame:
    """Load the selected signals for this strategy block and date."""
    signal_dir = ENG_ROOT / cfg["signal_dir"]
    date_tag   = signal_date.replace("-", "_")
    filename   = f"{cfg['selected_prefix']}__{date_tag}.csv"
    path       = signal_dir / filename

    if not path.exists():
        print(f"[journal_writer] selected signal file not found: {path}")
        print(f"[journal_writer] Run the nightly scan/selection first for {signal_date}.")
        return pd.DataFrame()

    df = pd.read_csv(path, dtype={"ticker": str})
    print(f"[journal_writer] loaded selected signals: {len(df)} row(s) from {filename}")
    return df


def load_ranked_pack(strategy_block: str, signal_date: str, cfg: dict) -> pd.DataFrame:
    """Load the full ranked / signal pack for the snapshot."""
    signal_dir = ENG_ROOT / cfg["signal_dir"]
    date_tag   = signal_date.replace("-", "_")
    filename   = f"{cfg['ranked_prefix']}__{date_tag}.csv"
    path       = signal_dir / filename

    if not path.exists():
        print(f"[journal_writer] ranked pack not found (snapshot skipped): {path}")
        return pd.DataFrame()

    df = pd.read_csv(path, dtype={"ticker": str})
    print(f"[journal_writer] loaded ranked pack: {len(df)} row(s) from {filename}")
    return df


# ── Journal write helpers ──────────────────────────────────────────────────────

def load_existing_journal_ids() -> set:
    """Return the set of journal_ids already in the canonical journal (dedup guard)."""
    if not CANONICAL_JOURNAL.exists():
        return set()
    try:
        df = pd.read_csv(CANONICAL_JOURNAL, dtype=str, usecols=["journal_id"])
        return set(df["journal_id"].dropna().str.strip())
    except Exception as exc:
        print(f"[journal_writer] warning: could not read existing journal ({exc}); treating as empty")
        return set()


def write_rows_to_journal(rows: list[dict], existing_ids: set) -> tuple[int, int]:
    """
    Append new rows to the canonical journal, skipping existing journal_ids.
    Returns (written_count, skipped_count).
    """
    CANONICAL_DIR.mkdir(parents=True, exist_ok=True)
    new_rows  = [r for r in rows if r["journal_id"] not in existing_ids]
    skip_rows = len(rows) - len(new_rows)

    mode      = "a" if CANONICAL_JOURNAL.exists() else "w"
    write_hdr = not CANONICAL_JOURNAL.exists()

    with open(CANONICAL_JOURNAL, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=JOURNAL_FIELDS, extrasaction="ignore")
        if write_hdr:
            writer.writeheader()
        for row in new_rows:
            writer.writerow(row)

    return len(new_rows), skip_rows


def write_dated_entries(rows: list[dict], variant_short: str, signal_date: str) -> None:
    """Write a dated snapshot of this run's journal entries (for GitHub Actions artifact use)."""
    JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
    date_tag = signal_date.replace("-", "_")
    path     = JOURNAL_DIR / f"journal_entries__{variant_short}__{date_tag}.csv"

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=JOURNAL_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    print(f"[journal_writer] dated entries  -> {path.name}  ({len(rows)} row(s))")


def write_ranked_snapshot(df: pd.DataFrame, variant_short: str, signal_date: str) -> None:
    """Write the full ranked pack as a frozen snapshot."""
    if df.empty:
        print(f"[journal_writer] ranked snapshot skipped (empty ranked pack)")
        return

    RANKED_SNAP_DIR.mkdir(parents=True, exist_ok=True)
    date_tag = signal_date.replace("-", "_")
    path     = RANKED_SNAP_DIR / f"ranked_snapshot__{variant_short}__{date_tag}.csv"

    if path.exists():
        print(f"[journal_writer] ranked snapshot already exists, skipping: {path.name}")
        return

    df.to_csv(path, index=False)
    print(f"[journal_writer] ranked snapshot -> {path.name}  ({len(df)} row(s))")


# ── Main ──────────────────────────────────────────────────────────────────────

def run(strategy_block: str, signal_date: str) -> None:
    if strategy_block not in _STRATEGY_CONFIGS:
        print(f"[journal_writer] ERROR: unknown strategy_block: {strategy_block}")
        print(f"[journal_writer] Allowed: {list(_STRATEGY_CONFIGS.keys())}")
        sys.exit(1)

    cfg           = _STRATEGY_CONFIGS[strategy_block]
    variant_short = cfg["variant_short"]
    run_id        = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    print(f"\n[journal_writer] strategy_block: {strategy_block}")
    print(f"[journal_writer] signal_date:     {signal_date}")
    print(f"[journal_writer] variant_short:   {variant_short}")
    print(f"[journal_writer] run_id:          {run_id}")

    # ── Load selected signals ──────────────────────────────────────────────────
    selected_df = load_selected_signals(strategy_block, signal_date, cfg)

    rows: list[dict] = []
    if not selected_df.empty:
        mapper = (
            map_gdt_v2_row if variant_short == "gdt_v2" else map_fbr_t002_row
        )
        for _, row in selected_df.iterrows():
            try:
                mapped = mapper(row, signal_date, run_id, variant_short, strategy_block, cfg)
                rows.append(mapped)
            except Exception as exc:
                ticker = str(row.get("ticker", "?"))
                print(f"[journal_writer] warning: skipping {ticker} due to mapping error: {exc}")

    print(f"[journal_writer] rows to journal: {len(rows)}")

    # ── Write dated entries (per-run artifact) ─────────────────────────────────
    write_dated_entries(rows, variant_short, signal_date)

    # ── Append to canonical journal (idempotent) ───────────────────────────────
    existing_ids = load_existing_journal_ids()
    written, skipped = write_rows_to_journal(rows, existing_ids)
    print(f"[journal_writer] canonical journal: {written} written, {skipped} skipped (duplicate)")
    print(f"[journal_writer] canonical journal path: {CANONICAL_JOURNAL}")

    # ── Write ranked snapshot ──────────────────────────────────────────────────
    ranked_df = load_ranked_pack(strategy_block, signal_date, cfg)
    write_ranked_snapshot(ranked_df, variant_short, signal_date)

    print(f"[journal_writer] done.\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="V1 trade journal writer for plan_next_day_day_trade blocks"
    )
    parser.add_argument(
        "--strategy-block",
        required=True,
        metavar="BLOCK",
        help=(
            "Full strategy block name. "
            "E.g. gap_directional_trap__bearish_medium_large__candidate_1_v2"
        ),
    )
    parser.add_argument(
        "--signal-date",
        required=True,
        metavar="YYYY-MM-DD",
        help="Signal date to journal.",
    )
    args = parser.parse_args()

    try:
        run(args.strategy_block, args.signal_date)
    except Exception as exc:
        # Never crash the pipeline — log and exit 0
        print(f"[journal_writer] ERROR: {exc}")
        import traceback
        traceback.print_exc()
        print("[journal_writer] Journal write failed. Pipeline continues.")
        sys.exit(0)


if __name__ == "__main__":
    main()
