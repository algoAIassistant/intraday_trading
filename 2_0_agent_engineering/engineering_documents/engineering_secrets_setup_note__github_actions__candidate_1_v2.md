# engineering_secrets_setup_note__github_actions__candidate_1_v2

document_type: setup_note
scope: GitHub Actions secrets required for nightly_gap_directional_trap_v2.yml
date: 2026-03-29

---

## Required secrets

Add these three secrets to your GitHub repo before the workflow can run.

**Where to add them:**
`GitHub repo → Settings → Secrets and variables → Actions → New repository secret`

| Secret name | What it is | Where to get it |
|-------------|------------|-----------------|
| `MASSIVE_API_KEY` | API key for the MASSIVE data provider | Your MASSIVE account dashboard |
| `TELEGRAM_BOT_TOKEN` | Token for the Telegram bot that sends messages | @BotFather on Telegram |
| `TELEGRAM_CHAT_ID` | Chat ID for the Telegram chat/channel to receive signals | See note below |

---

## How to find your TELEGRAM_CHAT_ID

**Option 1 — Personal chat with the bot:**
1. Start a chat with your bot in Telegram
2. Send a message to it
3. Visit: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
4. Look for `"chat": {"id": <number>}` in the response
5. That number is your TELEGRAM_CHAT_ID

**Option 2 — Group or channel:**
1. Add the bot to your group/channel
2. Send a message in the group/channel
3. Visit the getUpdates URL above
4. Look for the group's `chat.id` (negative number for groups)

---

## Verifying the secrets work

After adding secrets, run a manual test:

1. Go to your GitHub repo → Actions tab
2. Click `Nightly Gap Directional Trap v2`
3. Click `Run workflow`
4. Set `Preview only` = `true` (this prints the message without sending)
5. Set `Skip Stage 0 data refresh` = `true` (only if data is already cached)
6. Click `Run workflow`
7. Check the workflow logs — you should see the formatted Telegram message printed

If preview works, run again with `Preview only` = `false` to confirm the actual Telegram send.

---

## Workflow schedule

The workflow runs at **20:35 UTC = 4:35 PM ET** on Mon–Fri.

To change the schedule, edit the `cron` value in:
`.github/workflows/nightly_gap_directional_trap_v2.yml`

UTC offset guide:
- ET (standard / winter) = UTC-5 → 4:35 PM ET = 21:35 UTC
- ET (daylight / summer)  = UTC-4 → 4:35 PM ET = 20:35 UTC

The current setting `35 20 * * 1-5` targets summer (EDT) time.
During standard time (winter), change to `35 21 * * 1-5`.

---

## First-run data fetch

On the first run with no cache, Stage 0 will fetch daily OHLCV history from scratch
for all ~1,400 tickers in the operational universe (default_start: 2021-03-25).

This first fetch takes longer (30–60 min depending on API rate limits).
Subsequent runs are incremental — only new days are fetched.

The parquet data cache is stored via `actions/cache`. It persists between runs
and is keyed by date. If the cache expires (7 days of no access by default),
the next run fetches from scratch again automatically.

---

## Secrets are never logged

The workflow does not print secret values. All three secrets are passed via
environment variables only to the Python scripts that need them.
