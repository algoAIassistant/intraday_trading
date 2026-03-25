# Family Output Contract: failed_opening_drive_and_reclaim

This file defines what outputs this family must produce, where they must live, and how they must be named.

---

## Required outputs by phase

**phase_r0**
- Baseline return distribution file(s) for the target universe
- A written summary note documenting the baseline findings and the go/no-go decision

**phase_r1**
- One output file per condition tested, containing the conditioned return distribution and comparison to baseline
- A written summary note for each condition: measurable lift or no lift

**phase_r2**
- Year-by-year breakdown output for any condition that passed phase_r1
- Bucket breakdown output (cap tier, volume tier, or defined segmentation)
- Market context overlay output
- A structural stability summary note

**phase_r3**
- A formalized strategy definition document (entry, exit, stop, profit-taking, time-based exit)
- An initial in-sample expectancy output
- A written summary noting parameter choices and why they are not overfit

**phase_r4**
- Slippage sensitivity output
- Ticker concentration output
- Tail behavior / drawdown output
- Out-of-sample test output
- Final go/no-go recommendation note

---

## Output location

All outputs for this family live under:

```
1_0_strategy_research/research_outputs/family_lineages/failed_opening_drive_and_reclaim/
```

Outputs must mirror the branch lineage exactly:

```
family_lineages/
└── failed_opening_drive_and_reclaim/
    ├── phase_r0_baseline/
    ├── parent_001_<descriptive_name>/
    │   ├── phase_r1_conditional/
    │   ├── phase_r2_structural/
    │   ├── child_001_<descriptive_name>/
    │   │   ├── phase_r3_formalization/
    │   │   └── phase_r4_robust_validation/
    │   └── child_002_<descriptive_name>/
    └── parent_002_<descriptive_name>/
```

Do not dump outputs from multiple branches into the same folder.
Each branch has its own output folder.

---

## Output naming expectations

Output files must follow the project naming standard:

```
research_output_<family>__<phase>__<description>__<YYYY_MM_DD>.<ext>
```

Examples:
```
research_output_failed_opening_drive_and_reclaim__phase_r0_baseline__same_day_return_distribution__2026_03_24.csv
research_output_failed_opening_drive_and_reclaim__phase_r1_conditional__volume_surge_filter__2026_04_01.csv
research_output_failed_opening_drive_and_reclaim__phase_r2_structural__year_by_year_breakdown__2026_04_15.csv
```

No cryptic names. No version suffixes without documentation.

---

## Non-overwrite rule

No output may silently overwrite prior evidence.

- If a study is re-run with updated parameters, save the new output under a new filename with a new date.
- If a prior output is superseded, note the supersession in the lineage notes — do not delete the prior output.
- Archive outputs that belong to closed branches; do not delete them.
