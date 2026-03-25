# AI Trading Assistant

Research-to-engineering ecosystem for same-day intraday U.S. common-stock strategy discovery, validation, and production integration.

---

## Active flagship track

**`intraday_same_day`** — same-day entry and exit only, flat by close.

Secondary track (`swing_secondary`) is reference/inactive unless explicitly opened.

---

## Repository structure

```
ai_trading_assistant/
├── CLAUDE.md                         # Repo constitution and operating rules
├── README.md                         # This file
├── .gitignore
├── .claude/
│   ├── settings.local.json           # Local Claude Code settings
│   └── rules/                        # Scoped operating rules
│       ├── research_rules.md
│       ├── engineering_rules.md
│       ├── naming_rules.md
│       └── protected_files_rules.md
│
├── 0_0_work_protocols/               # Operating rules, handoff conventions, coordination docs
├── 0_1_shared_master_universe/       # Shared symbol lists, calendars, reference configs
├── 1_0_strategy_research/            # All research — studies, outputs, lineage trees
├── 2_0_agent_engineering/            # Production code — frozen survivors only
└── 9_0_archive/                      # Retired variants and deprecated material
```

---

## Research phase model (intraday_same_day)

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
- No overnight leakage into the flagship intraday track.
- Every branch must be traceable through the lineage model: `track → family → parent → child → grandchild`.
- All names are lowercase, underscore-separated, and human-readable.
- Dates use `YYYY_MM_DD` format.

See [CLAUDE.md](CLAUDE.md) for the full repo constitution.
