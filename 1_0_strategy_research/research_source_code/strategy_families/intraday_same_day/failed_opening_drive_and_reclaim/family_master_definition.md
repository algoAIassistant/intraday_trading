# Family Definition: failed_opening_drive_and_reclaim

Track: `intraday_same_day`
Family folder: `strategy_families/intraday_same_day/failed_opening_drive_and_reclaim/`

---

## What this family studies

This family studies a specific intraday price sequence:

1. The stock makes a directional drive early in the session — typically within the first 30–90 minutes — in one direction.
2. That drive fails to hold. Price reverses back through a key level (e.g., the opening range boundary, a VWAP zone, or a session high/low).
3. The reclaim of the prior level — or the failure to reclaim it — becomes the actionable signal.

The family investigates whether this failure-and-reclaim sequence produces a statistically measurable, repeatable edge in same-day price behavior on liquid U.S. common stocks.

---

## Why this belongs to intraday_same_day

- The entire sequence (drive, failure, reclaim) plays out within a single trading session.
- All entries and exits are same-day. The position is flat by close.
- No overnight exposure is assumed or permitted.
- The pattern depends on intraday price structure, not multi-day trend or gap behavior.

---

## What belongs in this family

- Studies of the failed drive sequence and its subsequent intraday behavior
- Conditional tests built on top of this sequence (volume, volatility, opening range width, market context)
- Structural validation of any edge found in phase_r1
- Formalized strategy variants that survived phases r0 through r2
- Branch variants that modify a confirmed parent edge

---

## What does not belong in this family

- Multi-day or overnight strategies — those belong in `swing_secondary`
- Generic gap studies not tied to the drive-and-reclaim sequence
- Engineering code of any kind
- Exploratory studies unrelated to the failed drive pattern
- Untracked temporary files or dead-end scripts without a lineage note
