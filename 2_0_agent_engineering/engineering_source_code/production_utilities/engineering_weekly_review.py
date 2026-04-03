"""
engineering_weekly_review.py

Weekly automated review output for canonical_trade_journal_v1.

Reads resolved rows from canonical_trade_journal_v1.csv and produces a
per-ISO-week markdown summary.

Row eligibility:
  Only rows with resolved_status in [not_triggered, stop, target, time_exit].
  Rows with resolved_status = 'unresolved' or 'manual_skip' are excluded.

Rows are grouped by trade_date (the execution day), not signal_date.
Weeks follow ISO calendar (Monday through Sunday).

Metrics per week:
  - total_signals, triggered, trigger_rate
  - exit_reason_counts
  - avg_r_triggered, avg_r_all
  - avg_roi_pct_triggered
  - per-block breakdown (gdt_v2, fbr_t002)
  - regime breakdown
  - warning flag summary

Output:
  engineering_runtime_outputs/plan_next_day_day_trade/trade_journal/
    weekly_reviews/
      weekly_review__{YYYY_WNN}.md

Spec:
  engineering_documents/engineering_spec__weekly_review_v1.md

Usage:
  # Auto-detect most recent week with at least one resolved row
  python engineering_weekly_review.py

  # Specific ISO week
  python engineering_weekly_review.py --week 2026-W14

  # All weeks present in the journal
  python engineering_weekly_review.py --all-weeks
"""

import argparse
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ENG_ROOT    = Path(__file__).resolve().parents[2]   # 2_0_agent_engineering/
# Canonical journal — repo-persistent source of truth (git-tracked)
CANONICAL   = ENG_ROOT / "engineering_trade_journal" / "canonical_trade_journal_v1.csv"
# Per-run artifact outputs (gitignored — ephemeral)
REVIEW_DIR  = ENG_ROOT / "engineering_runtime_outputs" / "plan_next_day_day_trade" / "trade_journal" / "weekly_reviews"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
RESOLVED_STATUSES  = {"not_triggered", "stop", "target", "time_exit"}
TRIGGERED_STATUSES = {"stop", "target", "time_exit"}
EXIT_ORDER         = ["not_triggered", "stop", "target", "time_exit", "manual_skip"]


# ---------------------------------------------------------------------------
# Week utilities
# ---------------------------------------------------------------------------

def _iso_week_label(d: date) -> str:
    """Return 'YYYY_WNN' for a date (e.g. '2026_W14')."""
    iso = d.isocalendar()
    return f"{iso.year}_W{iso.week:02d}"


def _iso_week_display(label: str) -> str:
    """Convert '2026_W14' to '2026-W14'."""
    return label.replace("_W", "-W")


def _parse_week_arg(s: str) -> str:
    """Parse '--week 2026-W14' and return the internal key '2026_W14'."""
    s = s.strip()
    if "-W" not in s:
        raise argparse.ArgumentTypeError(
            f"--week must be in YYYY-WNN format (e.g. 2026-W14), got: {s!r}"
        )
    return s.replace("-W", "_W")


def _week_date_range(rows: pd.DataFrame) -> str:
    """Return 'YYYY-MM-DD to YYYY-MM-DD' for the trade_dates in rows."""
    dates = sorted(rows["trade_date"].dropna().unique())
    if not dates:
        return "—"
    return f"{dates[0]} to {dates[-1]}"


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

def _prep_df(df: pd.DataFrame) -> pd.DataFrame:
    """Add computed columns needed for metrics. Returns a copy."""
    df = df.copy()

    # Numeric realized_r (already 0.0 for not_triggered)
    df["realized_r_f"] = pd.to_numeric(df["realized_r"], errors="coerce").fillna(0.0)

    # Numeric risk_pct (stored as a fraction, e.g. 0.0275)
    df["risk_pct_f"] = pd.to_numeric(df["risk_pct"], errors="coerce").fillna(0.0)

    # Estimated ROI pct for triggered rows = realized_r * risk_pct * 100
    df["roi_pct"] = df["realized_r_f"] * df["risk_pct_f"] * 100.0

    # Warning present flag
    df["has_warning"] = df["warning_flags"].apply(
        lambda v: bool(str(v).strip() and str(v).strip().lower() not in ("nan", ""))
    )

    return df


def _compute_metrics(rows: pd.DataFrame) -> dict:
    """Compute all review metrics for a slice of eligible resolved rows."""
    n = len(rows)
    if n == 0:
        return {"n": 0}

    triggered = rows[rows["resolved_status"].isin(TRIGGERED_STATUSES)]
    n_trig = len(triggered)

    avg_r_all  = rows["realized_r_f"].mean()
    avg_r_trig = triggered["realized_r_f"].mean() if n_trig > 0 else float("nan")
    avg_roi    = triggered["roi_pct"].mean()       if n_trig > 0 else float("nan")

    exit_counts = rows["resolved_status"].value_counts().to_dict()

    return {
        "n":                      n,
        "n_triggered":            n_trig,
        "trigger_rate":           n_trig / n,
        "exit_counts":            exit_counts,
        "avg_r_all":              avg_r_all,
        "avg_r_triggered":        avg_r_trig,
        "avg_roi_pct_triggered":  avg_roi,
    }


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _fmt_pct(v) -> str:
    try:
        return f"{float(v) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_r(v) -> str:
    try:
        f = float(v)
        return f"{f:+.3f}" if not (f != f) else "—"  # NaN check
    except (TypeError, ValueError):
        return "—"


def _fmt_roi(v) -> str:
    try:
        f = float(v)
        return f"{f:+.2f}%" if not (f != f) else "—"
    except (TypeError, ValueError):
        return "—"


def _render_metrics_table(m: dict) -> str:
    if m.get("n", 0) == 0:
        return "_No eligible resolved rows._\n"
    lines = [
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total signals | {m['n']} |",
        f"| Triggered | {m['n_triggered']} |",
        f"| Trigger rate | {_fmt_pct(m['trigger_rate'])} |",
        f"| Avg R (triggered) | {_fmt_r(m['avg_r_triggered'])} |",
        f"| Avg R (all resolved) | {_fmt_r(m['avg_r_all'])} |",
        f"| Avg est. ROI% (triggered) | {_fmt_roi(m['avg_roi_pct_triggered'])} |",
    ]
    return "\n".join(lines) + "\n"


def _render_exit_table(exit_counts: dict) -> str:
    lines = [
        "| Status | Count |",
        "|--------|-------|",
    ]
    for status in EXIT_ORDER:
        c = exit_counts.get(status, 0)
        if c > 0:
            lines.append(f"| {status} | {c} |")
    # Any unexpected status values
    for status, c in sorted(exit_counts.items()):
        if status not in EXIT_ORDER and c > 0:
            lines.append(f"| {status} | {c} |")
    return "\n".join(lines) + "\n"


def _render_split_table(rows: pd.DataFrame, split_col: str) -> str:
    groups = sorted(rows[split_col].fillna("(unknown)").unique())
    header = "| Group | Signals | Triggered | Trig% | Avg R (trig) | Avg R (all) |"
    sep    = "|-------|---------|-----------|-------|--------------|-------------|"
    lines  = [header, sep]
    for g in groups:
        m = _compute_metrics(rows[rows[split_col].fillna("(unknown)") == g])
        lines.append(
            f"| {g} | {m['n']} | {m['n_triggered']} "
            f"| {_fmt_pct(m['trigger_rate'])} "
            f"| {_fmt_r(m['avg_r_triggered'])} "
            f"| {_fmt_r(m['avg_r_all'])} |"
        )
    return "\n".join(lines) + "\n"


def _render_warning_table(rows: pd.DataFrame) -> str:
    n_warn    = rows["has_warning"].sum()
    n_no_warn = (~rows["has_warning"]).sum()
    lines = [
        "| Warning present | Count |",
        "|----------------|-------|",
        f"| yes | {n_warn} |",
        f"| no | {n_no_warn} |",
    ]
    # Top warning strings
    warned_rows = rows[rows["has_warning"]]
    if len(warned_rows) > 0:
        top = (
            warned_rows["warning_flags"]
            .str.strip()
            .value_counts()
            .head(5)
        )
        lines.append("")
        lines.append("Top warning flag strings:")
        lines.append("")
        for flag_str, cnt in top.items():
            truncated = flag_str[:80] + "..." if len(flag_str) > 80 else flag_str
            lines.append(f"- ({cnt}x) {truncated}")
    return "\n".join(lines) + "\n"


def render_report(week_label: str, rows: pd.DataFrame) -> str:
    """Render the full markdown report for one ISO week."""
    week_display  = _iso_week_display(week_label)
    generated_at  = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    date_range    = _week_date_range(rows)
    n_eligible    = len(rows)

    overall = _compute_metrics(rows)

    lines = [
        f"# Weekly Review — {week_display}",
        f"",
        f"generated_at: {generated_at}",
        f"trade_dates: {date_range}",
        f"resolved_rows_in_week: {n_eligible}",
        f"",
    ]

    if n_eligible == 0:
        lines.append("_No eligible resolved rows for this week._")
        return "\n".join(lines) + "\n"

    lines += [
        "---",
        "",
        "## Overall",
        "",
        _render_metrics_table(overall),
        "",
        "## Exit reason breakdown",
        "",
        _render_exit_table(overall["exit_counts"]),
        "",
        "## Per-block summary",
        "",
        _render_split_table(rows, "variant_short"),
        "",
        "## Regime summary",
        "",
        _render_split_table(rows, "market_regime_label"),
        "",
        "## Warning flag summary",
        "",
        _render_warning_table(rows),
    ]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def load_eligible_rows() -> pd.DataFrame:
    """Load canonical journal and return only eligible resolved rows."""
    if not CANONICAL.exists():
        print(f"[weekly_review] canonical journal not found: {CANONICAL}")
        sys.exit(1)

    df = pd.read_csv(CANONICAL, dtype=str).fillna("")
    eligible = df[df["resolved_status"].isin(RESOLVED_STATUSES)].copy()

    if len(eligible) == 0:
        return eligible

    # Parse trade_date to date objects (needed for ISO week grouping)
    eligible["_trade_date_obj"] = pd.to_datetime(
        eligible["trade_date"], errors="coerce"
    ).dt.date

    # Drop rows where trade_date could not be parsed
    eligible = eligible.dropna(subset=["_trade_date_obj"])

    # Add ISO week label
    eligible["_week"] = eligible["_trade_date_obj"].apply(_iso_week_label)

    return _prep_df(eligible)


def write_report(week_label: str, report_text: str) -> Path:
    """Write report markdown file. Returns the output path."""
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REVIEW_DIR / f"weekly_review__{week_label}.md"
    out_path.write_text(report_text, encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Weekly review report from canonical trade journal"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--week",
        metavar="YYYY-WNN",
        default=None,
        help="Produce report for this ISO week only (e.g. 2026-W14).",
    )
    group.add_argument(
        "--all-weeks",
        action="store_true",
        help="Produce reports for every ISO week present in the journal.",
    )
    args = parser.parse_args()

    eligible = load_eligible_rows()
    print(f"[weekly_review] eligible resolved rows: {len(eligible)}")

    if len(eligible) == 0:
        print("[weekly_review] No eligible rows. Nothing to report.")
        print("[weekly_review] Rows become eligible once Stage 5 auto-resolver runs.")
        return

    weeks_present = sorted(eligible["_week"].unique())

    if args.week:
        try:
            target_key = _parse_week_arg(args.week)
        except argparse.ArgumentTypeError as exc:
            print(f"[weekly_review] ERROR: {exc}")
            sys.exit(1)
        weeks_to_run = [target_key]
    elif args.all_weeks:
        weeks_to_run = weeks_present
    else:
        # Default: most recent week with at least one resolved row
        weeks_to_run = [weeks_present[-1]]
        print(f"[weekly_review] auto-selected week: {_iso_week_display(weeks_to_run[0])}")

    for week_label in weeks_to_run:
        week_rows = eligible[eligible["_week"] == week_label]
        report    = render_report(week_label, week_rows)
        out_path  = write_report(week_label, report)
        print(
            f"[weekly_review] {_iso_week_display(week_label)}: "
            f"{len(week_rows)} row(s) -> {out_path.name}"
        )

    print(f"[weekly_review] done. Reports in: {REVIEW_DIR}")


if __name__ == "__main__":
    main()
