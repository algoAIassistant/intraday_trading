# Project Master: Research–Engineering Boundary

---

## The boundary is permanent

Research and engineering are two separate sides of this project.
They are never mixed, even temporarily. There is no gray zone.

---

## What research may do

- Discover and explore market behavior
- Test conditions, filters, and observables
- Reject branches that do not survive
- Formalize surviving edges into defined strategies
- Produce validation artifacts and lineage notes
- Archive failed work with context

Research lives entirely in: `1_0_strategy_research/`

---

## What engineering may do

- Implement frozen research survivors as runnable modules
- Build execution infrastructure: dispatch, ranking, risk, broker adapters
- Write tests for implemented modules
- Operate the production system

Engineering lives entirely in: `2_0_agent_engineering/`

---

## What engineering may not do

- Invent strategy logic
- Add exploratory or hypothesis-testing code
- Import or copy research-phase code without explicit promotion
- Begin any work until at least one frozen survivor exists

---

## What belongs where

**In `1_0_strategy_research/`**
- Data cache and cache builders
- Baseline studies, conditional studies, structural validation scripts
- Strategy formalization scripts
- Robust validation scripts
- Research outputs and lineage trees
- Strategy family folders with all variants

**In `2_0_agent_engineering/`**
- Frozen, promoted strategy modules
- Market climate engine
- Strategy dispatcher and ranking engine
- Risk engine
- Signal runners
- Broker execution adapters
- Notifications
- Engineering tests

**Not in either**
- Shared symbol lists, calendars, and reference configs → `0_1_shared_master_universe/`
- Operating rules and handoff docs → `0_0_work_protocols/`
- Retired and deprecated material → `9_0_archive/`

---

## Promotion rule

A research variant may be promoted to engineering candidate when all of the following are true:

1. It has passed phase_r0 through phase_r4 without being closed.
2. It has a defined entry, exit, stop, and time-based exit rule (phase_r3 complete).
3. It has passed robust validation including slippage and out-of-sample testing (phase_r4 complete).
4. The user has explicitly approved the promotion.
5. A frozen copy exists in `research_source_code/strategy_families/<track>/<family>/frozen_survivors/`.

Only after all five conditions are met may a corresponding module be created in `2_0_agent_engineering/integrated_strategy_modules/`.
