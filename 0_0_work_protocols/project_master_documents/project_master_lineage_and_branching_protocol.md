# Project Master: Lineage and Branching Protocol

---

## Lineage model

Every research branch follows this model:

```
track
└── family
    └── parent
        └── child
            └── grandchild
                └── further descendants if needed
```

There is no fixed limit on depth or branch count.
Any family can spawn many parents. Any parent can spawn many children. Any child can spawn many grandchildren.

---

## What this is not

This is not a fixed set of module slots.
Do not artificially limit research to a small number of pre-named branches.
The lineage expands as research demands.

---

## Required properties of every branch

- **Named explicitly.** The folder name must describe the branch in plain English.
- **Traceable.** The parent must be identifiable from the folder hierarchy and from lineage notes.
- **Resolved.** Every branch must eventually reach one of the defined status outcomes below.

A branch that is ambiguous, unnamed, or unresolved is a violation of this protocol.

---

## Status outcomes

Every branch must be assigned one of these four statuses:

| Status | Meaning |
|--------|---------|
| `active` | Currently being worked. Phase is open and in progress. |
| `promoted` | Passed all research phases. Frozen survivor exists. Eligible for engineering. |
| `closed_no_survivor` | Phase completed but no edge survived. Branch is closed with a summary note. |
| `archived_reference_only` | Moved to `9_0_archive/`. Not active. Kept for context and future reference. |

Status must be recorded in the lineage notes for that branch.

---

## How outputs mirror lineage

Research outputs must follow the same lineage structure as the source code.

```
research_outputs/
└── family_lineages/
    └── <family_name>/
        ├── parent_001/
        │   ├── child_001/
        │   └── child_002/
        └── parent_002/
```

Do not dump all outputs into a flat folder. Output location must match branch location.

---

## Naming reminder for lineage branches

- Use plain English, lowercase, underscore-separated.
- Name the branch for what it tests or what defines it, not for a sequence number alone.
- Sequence numbers (`parent_001`, `child_002`) are acceptable as suffixes when the descriptive name is already present.

**Good:**
```
failed_opening_drive_and_reclaim/parent_001_volume_threshold_filter/
```

**Bad:**
```
branch_a/
p1c2/
test_new/
```

---

## When to branch

Create a new child when:
- A meaningful parameter or condition is changed from the parent
- A different filter or observable is being tested
- The parent is closed and a new direction is being explored

Do not overwrite the parent. Branch from it.
