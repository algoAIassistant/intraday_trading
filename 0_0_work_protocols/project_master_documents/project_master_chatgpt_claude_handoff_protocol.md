# Project Master: ChatGPT–Claude Code Handoff Protocol

---

## Cooperation model

**ChatGPT**
Architecture, synthesis, master document creation, research framing, protocol design, and strategic decision-making.
Works at the planning and reasoning layer.

**Claude Code**
Repo inspection, file reads, file edits, command execution, implementation assistance, and repo state verification.
Works at the execution layer.

**User**
Final decision-maker and the bridge between both systems.
Carries decisions, outputs, and context between ChatGPT and Claude Code.

---

## Key constraint

ChatGPT and Claude Code do not communicate directly.
There is no live connection between them.
All coordination flows through the repository and through the user.

Claude Code treats committed repo documents as the authoritative source of project state.
ChatGPT treats the same documents as the reference for current architecture and decisions.

---

## Handoff method

Coordination happens through these channels, in order of reliability:

1. **Committed repo files** — the most durable and authoritative channel
2. **Master documents** in `0_0_work_protocols/project_master_documents/` — architecture, scope, protocols
3. **`CLAUDE.md`** — repo constitution, always loaded
4. **Chat wrap-ups** — summaries written at the end of a working session, passed by the user
5. **Targeted prompts** — the user carries specific decisions or outputs between environments as needed

If something is not in a committed file, it is not guaranteed to persist across sessions.

---

## Research chat header

When starting a new research session in either ChatGPT or Claude Code, use this header to establish context:

```
current_track:
current_family:
current_phase:
current_module:
current_bucket:
current_regime_assumption:
current_question:
success_criteria:
kill_criteria:
```

Fill in only what is known. Leave blank fields as blank rather than guessing.

**Field definitions:**

- `current_track` — `intraday_same_day` or `swing_secondary`
- `current_family` — name of the strategy family being worked
- `current_phase` — active research phase (`phase_r0` through `phase_r4` or `phase_e0_to_e2`)
- `current_module` — specific script, study, or module being worked on
- `current_bucket` — market cap tier, volume tier, or other segment being studied
- `current_regime_assumption` — market context assumption in effect (e.g., trending, range-bound, no assumption)
- `current_question` — the specific question this session is trying to answer
- `success_criteria` — what result would confirm progress and allow moving forward
- `kill_criteria` — what result would close this branch as a no-survivor

---

## When to use /clear or reset context

Use `/clear` or start a fresh session when:

- Switching from one strategy family to a completely different one
- Switching from research work to engineering work or vice versa
- The current context has accumulated stale assumptions from a prior task
- A branch has been closed and you are starting a new direction

Do not carry context from a closed branch into the next one. Start clean.
Bring only what is committed to the repo.
