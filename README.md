# Mail Digest

**Your inbox, summarized.**

Mail Digest helps you stay on top of email without living in your inbox. It fetches Gmail on a schedule, saves messages locally, classifies them into newsletters, community mail, and everything else, and writes clear AI-powered daily, weekly, and monthly reports—with a short summary posted to Slack.

## Features

- **Rolling 24-hour window**: at 6:00 p.m. local time, fetches inbox mail from 6:00 p.m. yesterday → 6:00 p.m. today
- **Local archive**: `emails/YYYY/YYYY-MM/YYYY-MM-DD/` (`.eml` + `.meta.json`); after save, Gmail messages are marked read and moved to Trash
- **Rule-based classification**: AlphaSignal + TLDR (`tldrnewsletter.com`) → Newsletter; `@lists.boost.org` → Community; else Other
- **AI reports**: Claude Code CLI or Cursor CLI (configurable)
- **Slack**: structured Block Kit summary via webhook
- **Aggregates**: weekly report on Sundays, monthly report on the last day of each month

## Requirements

- Python 3.11+
- [Gmail API](https://developers.google.com/gmail/api) OAuth credentials
- [Claude Code CLI](https://code.claude.com/docs/en/cli-usage) and/or [Cursor CLI](https://cursor.com/docs/cli/overview)
- Slack incoming webhook URL

## Setup

### 1. Clone and install

```bash
cd mail-digest
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -e ".[dev]"
```

### 2. Google Cloud / Gmail OAuth

1. Create a project in [Google Cloud Console](https://console.cloud.google.com/)
2. Enable **Gmail API**
3. Configure **OAuth consent screen**:
   - User type: **External** (personal Gmail) or **Internal** (Google Workspace only)
   - App name: any name (e.g. Mail Digest)
   - Add your email under **Test users** (required while app is in **Testing**)
4. Create **OAuth 2.0 Client ID** (Desktop app)
5. Download JSON and save as `credentials.json` in the project root

### 3. Environment

```bash
cp .env.example .env
```

Edit `.env`:

```
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ
```

### 4. Configure sender rules and settings

**Personal overrides (recommended)** — keep repo defaults in git, put your own settings in local files:

```bash
cp config/config.local.yaml.example config/config.local.yaml
cp config/sender_rules.local.yaml.example config/sender_rules.local.yaml
```

Edit `config/config.local.yaml` and `config/sender_rules.local.yaml`. Only include keys you want to change; they are **merged on top of** the base YAML files and are gitignored.

Example `config/config.local.yaml`:

```yaml
ai:
  provider: cursor

gmail:
  trash_after_save: false
```

Alternatively, point to a config file anywhere on disk:

```bash
# .env or shell
MAIL_DIGEST_CONFIG=D:\path\to\my-config.yaml
MAIL_DIGEST_SENDER_RULES=D:\path\to\my-sender-rules.yaml
```

You can also edit [`config/config.yaml`](config/config.yaml) and [`config/sender_rules.yaml`](config/sender_rules.yaml) directly if you do not need a separate personal file.

### 5. Authenticate Gmail

```bash
python -m email_analyzer auth
```

Opens a browser once; saves `token.json` for headless runs. The app uses the `gmail.modify` scope (read inbox, mark read, move to Trash). If you previously authenticated with read-only access, delete `token.json` and run `auth` again.

Gmail cleanup after each successful local save (toggle in `config/config.yaml`):

```yaml
gmail:
  mark_read_after_save: true
  trash_after_save: true

paths:
  email_retention_days: 0  # delete local archives older than N days; 0 = keep forever
```

### 6. Run manually

Trigger the full pipeline now (fetch → classify → report → Slack):

```bash
python -m email_analyzer trigger
```

Same as `run` — useful for scheduled jobs and scripts:

```bash
python -m email_analyzer run
```

Or via the installed console script:

```bash
mail-digest trigger
```

Backfill a specific report date (window ends 6 p.m. that day):

```bash
python -m email_analyzer trigger --date 2026-06-11
```

### 7. Windows Task Scheduler (6:00 p.m. daily)

```powershell
.\scripts\register_task.ps1
```

Test the scheduled script:

```powershell
powershell -File .\scripts\run_daily.ps1
```

## Output layout

| Artifact | Path |
|----------|------|
| Emails | `emails/YYYY/YYYY-MM/YYYY-MM-DD/{message_id}.eml` |
| Daily report | `daily_reports/YYYY/YYYY-MM/YYYY-MM-DD.md` |
| Weekly report | `weekly_reports/YYYY/YYYY-Www.md` |
| Monthly report | `monthly_report/YYYY/YYYY-MM.md` |
| Logs | `logs/YYYY-MM-DD.log` |

## Report format

Daily reports are **rich Markdown archives** with subsections, context, and per-item detail. Slack still receives a short block summary only — the full report stays on disk.

Daily reports use three sections:

- **Newsletter** — new tools and improvements/trends
- **Community** — highlights and announcements
- **Other** — summary and action items

Slack receives a block summary per section; the full Markdown report stays on disk.

## AI providers

| Provider | Config value | Binary |
|----------|--------------|--------|
| Claude Code | `claude` | `claude` |
| Cursor | `cursor` | `agent` |

Claude runs headless with `--bare --tools ""` so report text goes to stdout.

Cursor runs with `agent -p --mode ask`.

### Claude Code via OpenRouter

Set your OpenRouter key in `.env`:

```
OPENROUTER_API_KEY=sk-or-v1-...
```

In [`config/config.yaml`](config/config.yaml):

```yaml
ai:
  provider: claude
  openrouter:
    enabled: true
    base_url: https://openrouter.ai/api
```

The app passes these env vars to the `claude` subprocess automatically:

- `ANTHROPIC_BASE_URL=https://openrouter.ai/api`
- `ANTHROPIC_AUTH_TOKEN=<your OpenRouter key>`
- `ANTHROPIC_API_KEY=` (empty — required to avoid Anthropic auth conflicts)

Optional: pick models on OpenRouter:

```yaml
openrouter:
  model: openai/gpt-4o-mini
```

This sets Sonnet, Opus, and Haiku tiers to the same model (used by Claude Code for report generation). Alternatives: `openai/gpt-4.1-mini` (newer), `openai/gpt-4.1-nano` (cheapest).

Get a key at [openrouter.ai/keys](https://openrouter.ai/keys).

If you previously logged into Claude Code with Anthropic directly, run `claude`, then `/logout`, before using OpenRouter.

## Future: Slack bot

The `ReportNotifier` protocol in `src/email_analyzer/slack/base.py` allows swapping the webhook notifier for a Slack Bolt bot without changing job logic.

## Development

```bash
pytest
ruff check src tests
```

## Troubleshooting

### Error 403: access_denied — app has not completed Google verification

Your OAuth app is in **Testing** mode. Only **Test users** listed in Google Cloud Console can sign in.

Fix:

1. Open [Google Cloud Console](https://console.cloud.google.com/) → **APIs & Services** → **OAuth consent screen**
2. Under **Test users**, click **Add users**
3. Add the **exact Gmail address** you use to sign in (e.g. `you@gmail.com`)
4. Save, wait ~1 minute, then run again:

```bash
python -m email_analyzer auth
```

5. On the Google sign-in page, if you see “Google hasn’t verified this app”, click **Advanced** → **Go to … (unsafe)** — that is normal for a personal test app.

You do **not** need to publish the app or complete Google verification for personal use. Testing + your account as a test user is enough.

- **Token expired**: run `python -m email_analyzer auth` again
- **No Slack message**: check `SLACK_WEBHOOK_URL` in `.env`
- **AI CLI not found**: install Claude Code or Cursor CLI and verify `claude` / `agent` is on PATH
- **Task Scheduler OAuth**: ensure first auth was done in the same user context as the scheduled task
