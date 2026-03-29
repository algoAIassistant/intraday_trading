# engineering_operator_summary__candidate_1_v2__nightly_system

document_type: operator_summary
scope: gap_directional_trap__candidate_1_v2 nightly production system
date: 2026-03-29

---

## How the nightly system works (operator view)

Every weekday after market close, GitHub Actions automatically:

1. **Fetches** the latest daily OHLCV data for ~1,400 US common stocks
2. **Rebuilds** the market context model (bearish / neutral / bullish label for today)
3. **Scans** all tickers for v2 signals (4-condition gap trap filter)
4. **Ranks** signals and selects up to 3 best candidates (one per price bucket)
5. **Sends** a Telegram message with the trade plan for tomorrow

**You receive a Telegram message by ~4:45 PM ET each trading day.**

If no signals fire (regime is not bearish, or no qualifying setups), you get a brief "no signals" message so you know the system ran.

---

## What the Telegram message tells you

For each signal:
- Ticker + price bucket
- Entry price (buy stop)
- Stop price
- Target price (2R)
- Risk % and $ per share
- ADV and relative volume (quality indicators)
- Selection score (transparent ranking)

**Critical timing fields printed in the header of every message:**
- Activate: 13:15 ET (when to enable the order)
- Cancel if: not triggered by 13:30 ET
- Flatten by: 14:30 ET

---

## Your daily workflow

**Night before (after receiving Telegram):**
1. Review the signals (usually 0–3 per day; 0 is common, regime must be bearish)
2. For each signal you want to trade:
   - Compute shares: `account_risk_dollar / risk_dollar_per_share`
   - Place buy stop in TOS at entry_price
   - Attach stop bracket at stop_price
   - Attach limit bracket at target_price (OCO with stop)
   - Configure conditional order to activate at 13:15 ET
   - Set a reminder to cancel at 13:30 ET if not filled

**Trade day:**
- 13:15 ET: confirm order is active (or place if conditional not working)
- 13:30 ET: cancel if not triggered
- 14:30 ET: flatten any open position manually

**No live monitoring required before 13:15 ET.**

---

## Position sizing reminder

This is a **wide-stop** setup (~4.7% average risk distance).

At 1% account risk per trade, share count is:
`shares = account_risk_dollar / risk_dollar_per_share`

With a $100k account and 1% risk ($1,000):
`shares ≈ 1,000 / (entry * 0.047)`

This is far fewer shares than a typical 1–2% stop trade.
Confirm your sizing every time. Do not default to your usual share count.

---

## 2022 structural risk reminder

Sustained directional bear markets (like 2022) suppress this mechanism.
2022 produced -0.156R expectancy for this setup.
If market conditions resemble prolonged 2022-style bear, consider reducing
exposure or pausing manually. There is no automated gate for this.

---

## Developer summary (what changed in v2 vs v1)

| area | v1 | v2 |
|------|----|----|
| Signal logic | gap_up, cl<0.20, bearish, medium/large | identical |
| Entry formula | close × 1.002 | identical |
| Stop formula | 0.75 × range | identical |
| Target formula | 2R | identical |
| Entry activation | market open (day order) | 13:15 ET |
| Cancel rule | day order self-expires | cancel if not filled by 13:30 ET |
| Exit rule | MOC (market on close) | forced flatten at 14:30 ET |
| Runtime path | candidate_1_v1/ | candidate_1_v2/ |
| v1 status | reference only (not run) | n/a |
| automation | windows task scheduler (deprecated) | github actions (primary) |

---

## File map

| purpose | file |
|---------|------|
| Orchestrator (run this) | `2_0_agent_engineering/engineering_nightly_orchestrator__gap_directional_trap__candidate_1_v2.py` |
| GitHub Actions workflow | `.github/workflows/nightly_gap_directional_trap_v2.yml` |
| Data refresh (Stage 0) | `2_0_agent_engineering/engineering_daily_data_refresh__gap_directional_trap__candidate_1_v2.py` |
| Signal scan (Stage 1) | `integrated_strategy_modules/.../engineering_nightly_signal_scan__gap_directional_trap__candidate_1_v2.py` |
| Selection layer (Stage 2) | `integrated_strategy_modules/.../engineering_selection_layer__gap_directional_trap__candidate_1_v2.py` |
| Telegram delivery (Stage 3) | `engineering_source_code/notifications/telegram_delivery__gap_directional_trap__candidate_1_v2.py` |
| Secrets setup | `engineering_documents/engineering_secrets_setup_note__github_actions__candidate_1_v2.md` |
| v2 research spec | `research_outputs/.../phase_r8_engineering_handoff/variant_spec__gap_directional_trap__candidate_1_v2__phase_r8__2026_03_29.yaml` |
| Operator decision note | `research_outputs/.../phase_r8_engineering_handoff/handoff_note__candidate_1_v2_as_live_variant__2026_03_29.md` |
| Module manifest | `integrated_strategy_modules/.../engineering_module_manifest__gap_directional_trap__candidate_1_v2.md` |
| Python dependencies | `requirements.txt` (repo root) |

---

## Dry-run test command (local)

```bash
cd 2_0_agent_engineering

# Full pipeline preview (no Telegram send, no data refresh if data is fresh)
python engineering_nightly_orchestrator__gap_directional_trap__candidate_1_v2.py \
  --skip-refresh \
  --preview

# With data refresh
MASSIVE_API_KEY=your_key \
python engineering_nightly_orchestrator__gap_directional_trap__candidate_1_v2.py \
  --preview
```

---

## Before going live: checklist

- [ ] GitHub repo secrets set: MASSIVE_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
- [ ] Workflow enabled in GitHub Actions tab
- [ ] Manual `workflow_dispatch` test run completed in preview mode
- [ ] Manual `workflow_dispatch` test run completed with real Telegram send
- [ ] Telegram message received and verified on phone
- [ ] v1 orchestrator NOT scheduled or running
- [ ] Operator understands 13:15 / 13:30 / 14:30 ET manual steps in TOS
