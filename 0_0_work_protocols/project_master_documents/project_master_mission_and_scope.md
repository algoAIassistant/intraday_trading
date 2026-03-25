# Project Master: Mission and Scope

---

## Mission

Build a repeatable research-to-engineering ecosystem for same-day intraday U.S. common-stock strategy discovery, validation, and production integration.

The current flagship mission is to produce a reliable, documented, and reproducible intraday research machine for liquid U.S. common stocks — strategies that enter and exit within the same trading day and are flat by close.

---

## Active flagship track

**`intraday_same_day`**

- Same-day entry, same-day exit only.
- All flagship modules must be flat by close.
- No overnight leakage is permitted in this track, under any circumstances.

---

## Secondary track

**`swing_secondary`** — inactive unless explicitly opened by the user.
It is reference material and a future expansion path, not a current work surface.

---

## What is in scope now

- Same-day intraday strategy research on liquid U.S. common stocks
- Building the research machine: data layer, study layer, validation layer
- Establishing reproducible workflows for the `intraday_same_day` track
- Creating shared infrastructure: symbol universe, market calendars, reference configs
- Archiving failed branches with documented context

---

## What is explicitly out of scope now

- Swing, options, futures, crypto, or multi-day strategies (unless the user explicitly opens them)
- Live broker execution or order routing (belongs in engineering, not active yet)
- Strategy invention without prior statistical evidence
- Engineering work before research survival

---

## Top-level workspace sections

| Folder | Role |
|--------|------|
| `0_0_work_protocols` | Operating rules, handoff conventions, repo protocols, coordination docs |
| `0_1_shared_master_universe` | Symbol lists, metadata, market calendars, reference configs |
| `1_0_strategy_research` | All research — studies, outputs, lineage trees, validation artifacts |
| `2_0_agent_engineering` | Production code — frozen research survivors only |
| `9_0_archive` | Retired variants, deprecated scripts, reference-only historical material |

---

## What stays true

- **Raw behavior first, strategy second.** Understand what the market does before formalizing a strategy.
- **Cache-first.** Do not re-fetch data that already exists in the cache.
- **Deterministic research.** Same inputs must produce same outputs, always.
- **One file at a time.** Inspect the exact target before touching anything.
- **No guessed paths.** Verify file existence before referencing or editing.
- **Engineering only after research survival.** No exceptions.
