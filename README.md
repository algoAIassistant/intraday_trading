# AI Trading Assistant

Research-to-engineering ecosystem for U.S. common-stock strategy discovery, validation, and production integration.

---

## Tracks

This repository supports multiple research and production tracks.

| Track | Status | Description |
|-------|--------|-------------|
| `plan_next_day_day_trade` | **Active — live automation running** | Night-before day-trade planning via TOS conditional orders. GitHub Actions nightly pipeline delivers Telegram signals. |
| `intraday_same_day` | Ongoing parallel research | Same-day entry and exit, flat by close. `failed_opening_drive_and_reclaim` family in phase_r1. |
| `swing_secondary` | Reference / inactive | Not the current focus. |

---

## Current live variant

**`gap_directional_trap__bearish_medium_large__candidate_1_v2`**

- Nightly scan runs after market close via GitHub Actions
- Delivers next-day bracket-order trade plans via Telegram
- Operator activates buy stop in TOS at 13:15 ET; cancels if not triggered by 13:30 ET; exits by 14:30 ET
- Validated expectancy: +0.773R (base), all years 2021–2026 positive
- Operator guide: [engineering_operator_summary__candidate_1_v2__nightly_system.md](2_0_agent_engineering/engineering_documents/engineering_operator_summary__candidate_1_v2__nightly_system.md)

---

## Repository structure

```text
ai_trading_assistant/
├── CLAUDE.md                         # Repo constitution and operating rules
├── README.md                         # This file
├── CURRENT_STATUS.md                 # Active track, family, variant at-a-glance
├── requirements.txt                  # Python dependencies (used by GitHub Actions)
├── .github/
│   └── workflows/
│       └── nightly_gap_directional_trap_v2.yml   # Nightly automation
├── .claude/
│   ├── settings.local.json
│   └── rules/                        # Scoped operating rules
├── 0_0_work_protocols/               # Operating rules, handoff conventions, master docs
├── 0_1_shared_master_universe/       # Shared symbol lists, metadata, reference configs
├── 1_0_strategy_research/            # All research — studies, outputs, lineage trees
├── 2_0_agent_engineering/            # Production code — frozen survivors only
└── 9_0_archive/                      # Retired variants and deprecated material
```

---

## Research phase model

### `plan_next_day_day_trade` phases

| Phase | Purpose |
|-------|---------|
| `r0` | Tradable universe foundation |
| `r1` | Market context model |
| `r2` | Family discovery and parent baseline |
| `r3` | Child isolation |
| `r4` | Grandchild parameter research |
| `r5` | Execution template research |
| `r6` | Deployable variant validation |
| `r8` | Research-to-engineering handoff |
| `e0` | Engineering integration |

### `intraday_same_day` phases

| Phase | Purpose |
|-------|---------|
| `phase_r0` | Intraday baseline — natural same-day behavior |
| `phase_r1` | Conditional behavior — one condition at a time |
| `phase_r2` | Structural validation — stability by year, window, bucket, context |
| `phase_r3` | Strategy formalization — entry, exit, stop, profit-taking, time exit |
| `phase_r4` | Robust validation — slippage, concentration, tails, out-of-sample |
| `phase_e0_to_e2` | Engineering — frozen survivors only |

Engineering begins only after research survival. No strategy logic is invented in engineering.

---

## Key rules

- Research and engineering are permanently separated.
- Every branch must be traceable: `track → family → parent → child → grandchild`.
- All names are lowercase, underscore-separated, and human-readable.
- Dates use `YYYY_MM_DD` format.

See [CLAUDE.md](CLAUDE.md) for the full repo constitution.
