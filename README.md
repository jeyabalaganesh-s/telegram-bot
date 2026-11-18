# Telegram Bot Inbox

Django application for receiving and managing Telegram conversations. It includes a conversation dashboard, message threads, text and media sending, incoming webhook handling, and complaint workflows.

## Stack

- Python and Django
- Django Channels for live updates
- Redis support for the channel layer
- Telegram Bot API
- SQLite configured in the project settings

## Run locally

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Set `SECRET_KEY`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_WEBHOOK_SECRET` in your local environment. Set `REDIS_URL` to enable the Redis-backed channel layer; without it, the project uses its configured fallback. Configure Telegram to send webhook updates to the deployed webhook route.

## App areas

- `telegram_app/` — conversations, messages, webhook, media, and dashboard
- `complaints/` — complaint records and related workflows
- `accounts/` — account and access views
