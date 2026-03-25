# Naming Rules

Scope: all files and folders in this repository.

---

## Required style

- Lowercase letters only for folder and file names.
- Words separated by underscores.
- Name must describe the purpose — make it readable without opening the file.
- Side of the project must be obvious from the name: `research_`, `engineering_`, `shared_`, or `archive_`.
- Dates use `YYYY_MM_DD` format.

## Allowed examples

```
research_run_intraday_baseline_study.py
research_config_intraday_same_day_phase_r0.yaml
engineering_dispatch_strategy_modules.py
engineering_config_signal_runner_prod.yaml
shared_master_symbol_list.csv
shared_market_calendar_us_2026.csv
validation_results__failed_opening_drive_and_reclaim__2026_03_24.csv
archive_retired_parent_001_notes.md
```

## Forbidden examples

```
sb1.py
mod_a.py
test2.py
tmp.py
final_final.py
rank_v3.py
new_script.py
backup.csv
```

## Versioning rule

Do not append version numbers unless the version means something documented.
If a version exists, a short note must explain what changed and why.

Avoid: `signal_runner_v3.py`
Use: `signal_runner_with_volume_filter.py` (or document the version explicitly)

## Lineage names

For strategy family folders, use plain-English descriptive names:

```
failed_opening_drive_and_reclaim/
opening_gap_fade_with_volume_confirmation/
```

Parent/child relationships must be explicit in folder hierarchy and lineage notes — not encoded in cryptic suffixes.

## Temporary and debug files

Temporary files must have a `tmp_` prefix and an associated task note.
Delete or archive them when the task is done.
Do not leave `tmp_`, `debug_`, or `test_` files as permanent repo residents.
