# Family Branch Registry: failed_opening_drive_and_reclaim

This file is the single source of truth for all branches in this family.
Update it whenever a branch is created, advanced, closed, or archived.

---

## Status definitions

| Status | Meaning |
|--------|---------|
| `active` | Branch is currently being worked. Phase is open and in progress. |
| `promoted` | Branch passed all research phases. Frozen survivor exists. Eligible for engineering. |
| `closed_no_survivor` | Branch completed but no edge survived. Closed with a summary note. |
| `archived_reference_only` | Moved to `9_0_archive/retired_research_variants/`. Not active. Kept for context. |

---

## Registry

### Branch: family_root

```
branch_name:        family_root
parent_branch:      (none — this is the family entry point)
status:             active
phase:              phase_r0
hypothesis_delta:   (baseline — no modification from family hypothesis)
promotion_reason:
closure_reason:
archive_location:
```

---

## How to add a new branch entry

Copy the template below and fill in all fields.
Leave `promotion_reason`, `closure_reason`, and `archive_location` blank until they apply.

```
branch_name:        <plain_english_name>
parent_branch:      <name_of_direct_parent_branch>
status:             active | promoted | closed_no_survivor | archived_reference_only
phase:              phase_r0 | phase_r1 | phase_r2 | phase_r3 | phase_r4 | phase_e0_to_e2
hypothesis_delta:   <what is different from the parent hypothesis — one sentence>
promotion_reason:   <what passed and why — fill when status = promoted>
closure_reason:     <what failed and what it implies — fill when status = closed_no_survivor>
archive_location:   <path in 9_0_archive — fill when status = archived_reference_only>
```

---

## Rules for this registry

- Every branch that exists as a folder must have an entry here.
- A branch without a registry entry is a lineage violation.
- Do not delete entries. If a branch is closed, update the status and fill the closure fields.
- Entries are append-only. Add new entries below existing ones.
- This file is updated by the user or by Claude Code on user instruction — not autonomously.
