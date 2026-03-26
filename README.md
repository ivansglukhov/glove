# Telegram Bot for Fencing Matchmaking

MVP scaffold for a Telegram bot that helps fencers find sparring partners, send duel invitations, record match results, and track per-weapon Elo ratings.

## Stack

- Python 3.12+
- `python-telegram-bot`
- `SQLAlchemy`
- `SQLite`

## Features planned in this scaffold

- User registration and profile storage
- Clubs catalog and seed data
- Per-weapon readiness statuses
- Invitations and matches
- Per-weapon Elo ratings
- Complaints and suggestions
- Admin-only section inside the bot

## Quick start

1. Create a virtual environment
2. Install dependencies
3. Copy `.env.example` to `.env`
4. Set `BOT_TOKEN` and `ADMIN_TELEGRAM_ID`
5. Run the seed command
6. Start the bot

Example:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
Copy-Item .env.example .env
python -m bot.seed
python -m bot.main
```

## Current project layout

- `bot/main.py` - Telegram app entrypoint
- `bot/config.py` - environment-based settings
- `bot/db.py` - SQLAlchemy engine and session helpers
- `bot/models.py` - database models
- `bot/enums.py` - shared enums
- `bot/handlers/` - Telegram handlers
- `bot/keyboards/` - reply and inline keyboards
- `bot/services/` - reusable business logic
- `bot/seed.py` - database creation and initial seed loading
- `seeds/` - JSON fixtures for clubs and test users

## What is implemented now

- App bootstrap
- SQLAlchemy schema
- Seed loading for clubs and test users
- Main menu
- Placeholder handlers for user/admin flows

## Suggested next steps

1. Finish registration conversation flow
2. Add search flow and filters
3. Add invitation lifecycle
4. Add match result confirmation flow
5. Add admin moderation actions
6. Add scheduled expiration and auto-draw jobs
