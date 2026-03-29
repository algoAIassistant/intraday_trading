# CLAUDE.md

## Project identity

- **Project:** AI Trading Assistant
- **Repo root:** `B:\git_hub\claude_code\ai_trading_assistant`
- **Current flagship track:** `intraday_same_day`
- **Secondary track:** `swing_secondary`
- **Primary objective:** build a repeatable research-to-engineering ecosystem for same-day intraday U.S. common-stock strategy discovery, validation, and later production integration.

## What this repository is for

This repository is not a random strategy sandbox.
It is a controlled trading-research and engineering workspace.

The default development logic is:

`market behavior -> statistical evidence -> structural validation -> strategy formalization -> robust validation -> engineering integration`

Do **not** reverse this into:

`idea -> code -> quick backtest -> new idea`

## Non-negotiable project rules

1. **Research and engineering stay permanently separated.**
2. **The active default track is `intraday_same_day`.**
3. **Flagship intraday work must enter and exit on the same trading day.**
4. **No overnight leakage into the flagship intraday track.**
5. **Engineering begins only after research survival.**
6. **Do not invent strategy logic in engineering folders or engineering chats.**
7. **Do not guess paths, filenames, or repo state. Inspect first.**
8. **Do not create cryptic names. Everything must stay human-readable.**
9. **Preserve lineage. Every parent/child/grandchild branch must remain traceable.**
10. **Prefer deterministic, cache-first research workflows.**

## Track policy

### `intraday_same_day` (active flagship)

Use this track by default unless the user explicitly says otherwise.

Rules:
- same-day entry and same-day exit only
- flat by close
- opening minutes are a variable to test, not an assumed universal edge
- stock-level observables come first
- market context is secondary during early discovery
- SPY/QQQ are validation overlays unless explicitly requested otherwise

### `swing_secondary`

This track is allowed but not the current default.
Use it only when the user explicitly opens swing work or when archival reference is needed.

### `plan_next_day_day_trade`

This track is for night-before day-trade planning via Thinkorswim conditional-order workflow.
When a session specifies `active track = plan_next_day_day_trade`, this track overrides the `intraday_same_day` default for that session.
Full phase model, track rules, and canonical doc pointers: `.claude/rules/plan_next_day_day_trade_rules.md`.
Do not shorten the track name. Do not revert to `intraday_same_day` defaults mid-session if this track is active.

## Top-level workspace structure

The repo should keep this permanent structure:

```text
B:\git_hub\claude_code\ai_trading_assistant
│
├── CLAUDE.md
├── README.md
├── .gitignore
├── .claude
│   ├── settings.local.json
│   └── rules
│       ├── research_rules.md
│       ├── engineering_rules.md
│       ├── naming_rules.md
│       └── protected_files_rules.md
│
├── 0_0_work_protocols
├── 0_1_shared_master_universe
├── 1_0_strategy_research
├── 2_0_agent_engineering
└── 9_0_archive
```

## Purpose of each top-level folder

### `0_0_work_protocols`
Holds master operating rules, handoff conventions, repo protocols, naming standards, and cross-platform coordination documents.

### `0_1_shared_master_universe`
Holds shared symbol lists, metadata, market calendars, reference configs, and validation artifacts used across the whole ecosystem.

### `1_0_strategy_research`
Holds all research-only logic, studies, outputs, family lineage trees, validation artifacts, and research documentation.

### `2_0_agent_engineering`
Holds production-side integration code, runtime configs, ranking/dispatch logic, notifications, broker adapters, and frozen modules that already survived research.

### `9_0_archive`
Holds retired variants, deprecated scripts, old wraps, and reference-only historical material.

## Research architecture: unlimited lineage, not fixed module slots

Do **not** structure research as a small fixed list of modules.
The architecture must support unlimited expansion.

Use this lineage model:

```text
track
└── family
    └── parent
        └── child
            └── grandchild
                └── further_descendants_if_needed
```

This means:
- any family can spawn many parents
- any parent can spawn many children
- any child can spawn many grandchildren
- there is no artificial cap on branch count
- lineage must remain readable and inspectable

## Recommended research family layout

```text
1_0_strategy_research
├── research_documents
├── research_configs
├── research_registry
├── research_data_cache
│   ├── daily
│   ├── intraday_1m
│   ├── market
│   └── coverage
├── research_outputs
│   ├── baseline_studies
│   ├── conditional_studies
│   ├── structural_validation
│   ├── strategy_formalization
│   ├── robust_validation
│   └── family_lineages
└── research_source_code
    ├── data_providers
    ├── cache_builders
    ├── universe_builder
    ├── baseline_market_studies
    ├── conditional_behavior
    ├── structural_pattern_studies
    ├── strategy_formalization
    ├── robust_validation
    ├── reporting
    └── strategy_families
        ├── intraday_same_day
        └── swing_secondary
```

## Example lineage pattern

```text
strategy_families
└── intraday_same_day
    └── failed_opening_drive_and_reclaim
        ├── family_definition
        ├── parent_variants
        │   ├── parent_001
        │   │   ├── child_001
        │   │   │   ├── grandchild_001
        │   │   │   └── grandchild_002
        │   │   ├── child_002
        │   │   └── lineage_notes
        │   └── parent_002
        ├── family_outputs
        └── frozen_survivors
```

## Research phase model

For the active flagship track, use this phase order unless the user explicitly overrides it:

- `phase_r0_intraday_baseline`
- `phase_r1_intraday_conditional_behavior`
- `phase_r2_intraday_structural_validation`
- `phase_r3_intraday_strategy_formalization`
- `phase_r4_intraday_robust_validation`
- `phase_e0_to_e2_engineering`

### Meaning of the phases

- **phase_r0** = understand same-day natural behavior first
- **phase_r1** = test one condition at a time
- **phase_r2** = keep only stable uplift by year, window, bucket, and context
- **phase_r3** = define exact entry, exit, stop, profit-taking, and time-based exit
- **phase_r4** = validate stability, slippage sensitivity, ticker concentration, tails, and out-of-sample behavior
- **phase_e0_to_e2** = only now engineer frozen survivors into runnable modules

## Engineering architecture

Engineering is not the place for fresh hypothesis generation.
Only research survivors move here.

Recommended layout:

```text
2_0_agent_engineering
├── engineering_documents
├── engineering_configs
├── engineering_source_code
│   ├── market_climate_engine
│   ├── strategy_dispatcher
│   ├── ranking_engine
│   ├── risk_engine
│   ├── signal_runners
│   ├── notifications
│   ├── broker_execution_adapters
│   └── production_utilities
├── engineering_tests
├── engineering_runtime_outputs
└── integrated_strategy_modules
    ├── intraday_same_day
    └── swing_secondary
```

## Naming rules

Use plain-English, human-readable names.

### Required naming style
- lowercase for subfolders and most filenames
- underscore-separated words
- descriptive purpose in the name
- research/engineering/shared/archive side must be obvious
- dates use `YYYY_MM_DD`

### Allowed style examples
- `research_run_intraday_baseline_study.py`
- `engineering_dispatch_strategy_modules.py`
- `shared_master_symbol_list.csv`
- `validation_results__failed_opening_drive_and_reclaim__2026_03_24.csv`

### Forbidden style examples
- `sb1.py`
- `mod_a.py`
- `test2.py`
- `tmp.py`
- `final_final.py`
- `rank_v3.py`

### Versioning rule
Do not add meaningless versions.
If a version exists, it must mean something and be documented.

## File creation and editing behavior for Claude

When working in this repo:

1. inspect the relevant tree before proposing edits
2. verify exact file paths before modifying anything
3. do not claim a file exists without checking
4. do not silently mix research-side and engineering-side code
5. keep changes scoped to the active task
6. prefer readable deterministic solutions over clever opaque ones
7. preserve lineage notes and prior outputs when extending a family
8. when creating a new branch, make the parent/child relationship explicit in names and folders
9. when a temporary debug or failed helper file is no longer needed, recommend deletion or archive it cleanly
10. do not leave behind junk files with vague names

## How Claude should collaborate with the user in this repo

Claude should act as the execution-side repo operator, not as a freeform idea generator detached from the codebase.

Default behavior:
- inspect repo state first
- summarize the exact target before major edits
- keep the user oriented about which side of the project is active
- respect the active track
- avoid long theory unless the user asks for it
- prefer practical next actions
- preserve continuity through clear notes and file naming

## How ChatGPT and Claude Code coordinate

There is **no direct machine-to-machine communication** between ChatGPT and Claude Code.
Coordination happens through:
- this repository
- `CLAUDE.md`
- scoped rule files
- master documents
- handoff notes
- the user carrying decisions between environments

Therefore, Claude must treat repo documents and committed rules as the source of persistent project coordination.

## Repo self-sufficiency rule

Do not rely on hidden memory or unstated conventions.
Important repo behavior should live in committed project instructions and readable files.
This repository should remain understandable to a future session without requiring private context.

## Future project rules

As the repo grows, more specific scoped rules may be added under `.claude/rules/`.
When such rules exist:
- keep them concise
- scope them by purpose
- do not duplicate large sections unnecessarily
- use the root `CLAUDE.md` as the repo constitution
- use scoped rules for narrower contexts such as research-only, engineering-only, naming-only, or protected-file behavior

## Default decision rule when uncertain

If uncertain between speed and structural clarity, choose structural clarity.
If uncertain between a new strategy hypothesis and market-first analysis, choose market-first analysis.
If uncertain whether something belongs in research or engineering, place it in research unless it is already a frozen survivor.

## Immediate startup interpretation for this repo

Until explicitly changed by the user, assume:
- active track = `intraday_same_day`
- active mission = build the same-day intraday research machine first
- swing remains reference/secondary
- research output should favor stock-level intraday observables first
- market context is validation context unless explicitly promoted later

## Session track override

If a session explicitly opens with `active track = plan_next_day_day_trade`:
- override the `intraday_same_day` default for that session only
- read `.claude/rules/plan_next_day_day_trade_rules.md` and the family tree master doc before proceeding
- do not revert to `intraday_same_day` defaults mid-session

