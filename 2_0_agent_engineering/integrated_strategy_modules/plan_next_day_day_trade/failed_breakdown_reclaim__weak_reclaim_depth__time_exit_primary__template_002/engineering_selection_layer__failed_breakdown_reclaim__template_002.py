"""
engineering_selection_layer__failed_breakdown_reclaim__template_002.py

track:    plan_next_day_day_trade
family:   failed_breakdown_reclaim
variant:  failed_breakdown_reclaim__weak_reclaim_depth__time_exit_primary__template_002

Purpose:
  Reads the raw signal pack, computes a simple selection score from fields
  already present in the signal pack (no parquet re-reads), and selects
  up to 3 signals for Telegram delivery.

  Does NOT modify the raw signal pack or any scan logic.

Score components:
  ADV score      (40%)  log10 scale; floor=$50M, ceil=$200M. Higher liquidity preferred.
  Risk score     (30%)  1 - risk_pct/0.15. Tighter stop preferred.
  Depth score    (15%)  depth_pct/0.03. Deeper breakdown preferred.
  Reclaim score  (15%)  (0.002 - reclaim_pct)/0.002. Closer to prior_day_low preferred.
  Penalty:       -0.15  for very_wide_stop flag.

  All inputs come from the signal pack — no external data reads required.

Inputs:
  engineering_runtime_outputs/plan_next_day_day_trade/
    failed_breakdown_reclaim__template_002/
      signal_pack__failed_breakdown_reclaim__template_002__YYYY_MM_DD.csv

Outputs:
  engineering_runtime_outputs/plan_next_day_day_trade/
    failed_breakdown_reclaim__template_002/
      selected_top_3__failed_breakdown_reclaim__template_002__YYYY_MM_DD.csv

Usage:
  python engineering_selection_layer__failed_breakdown_reclaim__template_002.py
  python engineering_selection_layer__failed_breakdown_reclaim__template_002.py --signal-date 2026-03-31
"""

import argparse
import math
import sys
from pathlib import Path

import pandas as pd

# ── Paths ──────────────────────────────────────────────────────────────────────
# File at: 2_0_agent_engineering/integrated_strategy_modules/plan_next_day_day_trade/
#          failed_breakdown_reclaim__weak_reclaim_depth__time_exit_primary__template_002/
# parents[4] = repo root
REPO_ROOT = Path(__file__).resolve().parents[4]

SIGNAL_PACK_DIR = (
    REPO_ROOT
    / "2_0_agent_engineering"
    / "engineering_runtime_outputs"
    / "plan_next_day_day_trade"
    / "failed_breakdown_reclaim__template_002"
)
OUTPUT_DIR = SIGNAL_PACK_DIR

SIGNAL_PACK_GLOB   = "signal_pack__failed_breakdown_reclaim__template_002__*.csv"
SIGNAL_PACK_PREFIX = "signal_pack__failed_breakdown_reclaim__template_002__"

MAX_DELIVERY = 3

# ── Score weights ──────────────────────────────────────────────────────────────
W_ADV     = 0.40
W_RISK    = 0.30
W_DEPTH   = 0.15
W_RECLAIM = 0.15

_ADV_LOG_FLOOR = math.log10(50_000_000)    # $50M — minimum allowed ADV bucket
_ADV_LOG_CEIL  = math.log10(200_000_000)   # $200M — practical ceiling
RISK_CAP       = 0.15    # 15% stop distance ceiling
DEPTH_CAP      = 0.030   # 3% breakdown depth ceiling
RECLAIM_CAP    = 0.002   # 0.2% — matches locked scan filter ceiling
PENALTY_WIDE   = 0.15    # penalty for very_wide_stop flag


# ── Score functions ────────────────────────────────────────────────────────────

def score_adv(adv: float) -> float:
    if adv <= 0:
        return 0.0
    raw = (math.log10(adv) - _ADV_LOG_FLOOR) / (_ADV_LOG_CEIL - _ADV_LOG_FLOOR)
    return max(0.0, min(1.0, raw))


def score_risk(risk_pct: float) -> float:
    """Tighter stop (lower risk_pct) scores higher."""
    return max(0.0, 1.0 - risk_pct / RISK_CAP)


def score_depth(depth_pct: float) -> float:
    """Deeper breakdown (more trapped shorts) scores higher."""
    return min(depth_pct / DEPTH_CAP, 1.0)


def score_reclaim(reclaim_pct: float) -> float:
    """Closing closer to prior_day_low (tighter trap) scores higher."""
    return max(0.0, (RECLAIM_CAP - reclaim_pct) / RECLAIM_CAP)


def compute_score(row: pd.Series) -> tuple[float, float]:
    """Return (raw_score, final_score_after_penalty)."""
    try:
        adv   = float(row["adv_dollar_approx"])
        risk  = float(row["risk_distance_pct"]) if str(row.get("risk_distance_pct", "")).strip() else 0.0
        depth = float(row["breakdown_depth_pct"])
        recl  = float(row["reclaim_pct"])
    except (ValueError, TypeError):
        return 0.0, 0.0

    raw = (
        W_ADV     * score_adv(adv)
        + W_RISK    * score_risk(risk)
        + W_DEPTH   * score_depth(depth)
        + W_RECLAIM * score_reclaim(recl)
    )
    penalty = PENALTY_WIDE if "very_wide_stop" in str(row.get("warning_flags", "")) else 0.0
    return round(raw, 4), round(raw - penalty, 4)


# ── File resolution ────────────────────────────────────────────────────────────

def find_signal_pack(signal_date: str | None) -> Path:
    if signal_date:
        date_tag = signal_date.replace("-", "_")
        p = SIGNAL_PACK_DIR / f"{SIGNAL_PACK_PREFIX}{date_tag}.csv"
        if not p.exists():
            print(f"[ERROR] signal pack not found: {p}")
            sys.exit(1)
        return p
    packs = sorted(SIGNAL_PACK_DIR.glob(SIGNAL_PACK_GLOB))
    if not packs:
        print("[ERROR] no signal pack found — run signal scan first")
        sys.exit(1)
    return packs[-1]


# ── Main selection ─────────────────────────────────────────────────────────────

def run_selection(signal_date: str | None = None) -> None:
    pack_path = find_signal_pack(signal_date)
    date_tag  = pack_path.stem.split("__")[-1]   # YYYY_MM_DD
    sig_date  = date_tag.replace("_", "-")

    print(f"\n{'='*66}")
    print(f"  failed_breakdown_reclaim  |  selection layer  |  {sig_date}")
    print(f"{'='*66}\n")

    df = pd.read_csv(pack_path, dtype=str)
    print(f"[load]  signal pack rows: {len(df)}")

    if df.empty:
        print("[result] no signals — writing empty selected_top_3")
        _write_empty(sig_date, date_tag)
        return

    # Score
    scores_raw   = []
    scores_final = []
    for _, row in df.iterrows():
        r, f = compute_score(row)
        scores_raw.append(r)
        scores_final.append(f)

    df["selection_score_raw"] = scores_raw
    df["selection_score"]     = scores_final
    df["selected_for_delivery"] = False

    df = df.sort_values("selection_score", ascending=False).reset_index(drop=True)

    for rank, idx in enumerate(df.index, start=1):
        df.at[idx, "selection_rank"] = rank

    top_n = min(MAX_DELIVERY, len(df))
    df.loc[df.index[:top_n], "selected_for_delivery"] = True

    top_df = df.loc[df.index[:top_n]].copy()

    print(f"[score] candidates: {len(df)}")
    print(f"[score] selected:   {top_n}")
    print()

    # Console summary
    hdr = f"  {'#':<3} {'Ticker':<8} {'ADV Bucket':<16} {'PriceBkt':<14} {'Entry':>7} {'Stop':>7} {'Risk%':>6} {'Score':>7}"
    print(hdr)
    print(f"  {'-'*70}")
    for rank, (_, row) in enumerate(top_df.iterrows(), start=1):
        risk_str = f"{float(row['risk_distance_pct'])*100:.1f}%" if str(row.get('risk_distance_pct', '')).strip() else "n/a"
        print(
            f"  {rank:<3} {row['ticker']:<8} {row['adv_dollar_bucket']:<16} "
            f"{row['price_bucket']:<14} "
            f"{float(row['entry_price']):>7.2f} {float(row['stop_price']):>7.2f} "
            f"{risk_str:>6} {float(row['selection_score']):>7.4f}"
        )
    print()

    # Write
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"selected_top_3__failed_breakdown_reclaim__template_002__{date_tag}.csv"
    top_df.to_csv(out_path, index=False)
    print(f"[output] {out_path.name}")
    print(f"\n[done]  selection complete  signal_date={sig_date}  selected={top_n}\n")


def _write_empty(sig_date: str, date_tag: str) -> None:
    out_path = OUTPUT_DIR / f"selected_top_3__failed_breakdown_reclaim__template_002__{date_tag}.csv"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(columns=[
        "signal_date", "trade_date", "ticker",
        "selected_for_delivery", "selection_score", "selection_rank",
    ]).to_csv(out_path, index=False)
    print(f"[output] {out_path.name}  (empty)")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Selection layer: failed_breakdown_reclaim__template_002"
    )
    parser.add_argument(
        "--signal-date",
        metavar="YYYY-MM-DD",
        default=None,
        help="Signal date. Defaults to latest signal pack.",
    )
    args = parser.parse_args()
    run_selection(signal_date=args.signal_date)


if __name__ == "__main__":
    main()
