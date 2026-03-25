# Engineering Rules

Scope: all work inside `2_0_agent_engineering/`.

---

## Entry condition

Engineering work begins only after a strategy has survived `phase_r4` (robust validation) in `1_0_strategy_research/`.

Do not create engineering code for strategies that are still in research phases.
Do not invent strategy logic inside engineering folders.

## What belongs here

Only frozen research survivors.
A frozen survivor is a strategy variant that has passed all five research phases and has been explicitly moved to `integrated_strategy_modules/` by the user.

## Engineering layout

```
2_0_agent_engineering/
├── engineering_documents/
├── engineering_configs/
├── engineering_source_code/
│   ├── market_climate_engine/
│   ├── strategy_dispatcher/
│   ├── ranking_engine/
│   ├── risk_engine/
│   ├── signal_runners/
│   ├── notifications/
│   ├── broker_execution_adapters/
│   └── production_utilities/
├── engineering_tests/
├── engineering_runtime_outputs/
└── integrated_strategy_modules/
    ├── intraday_same_day/
    └── swing_secondary/
```

## Behavior rules

- Do not silently mix research logic and engineering logic.
- Do not add research-phase exploratory code to engineering modules.
- Engineering code must be runnable, testable, and traceable to a named research survivor.
- Runtime outputs go in `engineering_runtime_outputs/` — do not commit large runtime dumps.
- Engineering tests go in `engineering_tests/` — keep them isolated from research source code.

## Change discipline

- Inspect exact file paths before modifying anything.
- Do not claim a file exists without checking.
- Scope changes to the active task only.
- When a temporary debug file is no longer needed, delete or archive it cleanly.
