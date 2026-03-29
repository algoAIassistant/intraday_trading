# CURRENT_STATUS

last_updated: 2026-03-29

---

## Active track

**plan_next_day_day_trade**

## Active family

**gap_directional_trap**

## Live variant

**gap_directional_trap__bearish_medium_large__candidate_1_v2**

---

## Automation

- GitHub Actions: `.github/workflows/nightly_gap_directional_trap_v2.yml`
- Schedule: Mon–Fri after market close (20:35 UTC = 4:35 PM EDT)
- Delivery: Telegram
- Operator steps: activate buy stop at 13:15 ET, cancel by 13:30 ET, flatten by 14:30 ET

## Phase status (gap_directional_trap family)

| Phase | Status |
|-------|--------|
| r0 — tradable universe foundation | complete |
| r1 — market context model | complete |
| r2 — family discovery and parent baseline | complete |
| r3 — child isolation | complete |
| r4 — grandchild parameter research | complete |
| r5 — execution template research | complete |
| r6 — deployable variant validation | complete |
| r8 — research-to-engineering handoff | complete |
| e0 — engineering integration | complete |

## Before going live: remaining manual steps

- [ ] Add GitHub repo secrets: MASSIVE_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
- [ ] Enable GitHub Actions workflow in the Actions tab
- [ ] Run workflow_dispatch test (preview=true first, then real send)
- [ ] Confirm Telegram message received and verified on phone

See [engineering_secrets_setup_note__github_actions__candidate_1_v2.md](2_0_agent_engineering/engineering_documents/engineering_secrets_setup_note__github_actions__candidate_1_v2.md)

---

## Parallel track

**intraday_same_day** — ongoing research (not the current live automation path)

- Family: failed_opening_drive_and_reclaim
- Current phase: phase_r1 (conditional behavior)
- No live automation; research only

---

## Key engineering files (v2 live path)

| Purpose | File |
|---------|------|
| GitHub Actions workflow | `.github/workflows/nightly_gap_directional_trap_v2.yml` |
| Orchestrator | `2_0_agent_engineering/engineering_nightly_orchestrator__gap_directional_trap__candidate_1_v2.py` |
| Signal scan | `2_0_agent_engineering/integrated_strategy_modules/plan_next_day_day_trade/gap_directional_trap__bearish_medium_large__candidate_1_v2/engineering_nightly_signal_scan__gap_directional_trap__candidate_1_v2.py` |
| Telegram delivery | `2_0_agent_engineering/engineering_source_code/notifications/telegram_delivery__gap_directional_trap__candidate_1_v2.py` |
| Operator guide | `2_0_agent_engineering/engineering_documents/engineering_operator_summary__candidate_1_v2__nightly_system.md` |
| Secrets setup | `2_0_agent_engineering/engineering_documents/engineering_secrets_setup_note__github_actions__candidate_1_v2.md` |
| Python dependencies | `requirements.txt` |
