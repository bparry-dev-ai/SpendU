# SpendU

A personal and family spending tracker: spending by card and category, a
monthly bills checklist, budgets, subscriptions, CSV import from your bank,
and charts. Self-hosted with Docker.

> **Disclaimer:** this is a learning and experimenting project. I'm a student
> building it to learn Python, SQL, web development, hosting, git and server
> management. Tips and suggestions are welcome!

## Features

- **Home dashboard**: this month's spending compared with last month, the
  week's total, family total, bills due, budgets, and subscriptions waiting
  to be confirmed.
- **Quick add**: amount, merchant (autocompletes and remembers the category
  you last used), category, card and date. Handles purchases, refunds and
  credits, bill payments, and subscription charges (including setting up a
  new subscription while logging its first charge).
- **Edit and delete** any transaction, plus notes on any entry.
- **Bills checklist**: set up each bill once (usual amount, due day,
  default card, monthly or yearly). Every month shows Paid, Due soon or
  Overdue, and "Mark paid" logs the payment with everything filled in.
- **Budget Planner**: enter your monthly income and split it into Needs,
  Wants and Savings, with a card for each budget area. Each card shows this
  month's spending and your 3-month average, with suggestions where you're
  over- or under-spending. Bills and subscriptions are added automatically.
  There's a personal plan each plus a shared household plan, and category
  cards double as monthly limits on Home.
- **Subscriptions**: repeating charges that wait for you to confirm (or
  skip) each one, so price changes are easy to catch.
- **Insights**: spending by category and card (donut and bar charts), top
  merchants, 12-month trends, a month-vs-month comparison, and a calendar
  heat map with bill due dates.
- **Activity**: full searchable, filterable history with CSV export.
- **CSV import**: presets for Apple Card, American Express, Navy Federal and
  Keesler Federal, plus manual column mapping. Duplicates and card payments
  are detected automatically.
- **Family profiles**: each person's spending is private; totals and family
  budgets are shared.
- **Sign-in**: password (rate-limited, optional 30-day "remember me") or
  Face ID / passkey.
- **Automatic database backups**: see [BACKUPS.md](BACKUPS.md).
- Light and dark mode, designed for phones first.

## Tech

| Part | What |
|---|---|
| Backend | Python 3.12, Flask (JSON API), SQLite, gunicorn |
| Frontend | React 18 + Vite, React Router, Chart.js, lucide icons |
| Hosting | Docker (two-stage build: Node builds the frontend, Python runs it) |

```
app.py                 entry point (gunicorn runs app:app)
spendu/                backend package
  __init__.py          app setup, security checks, CLI commands
  migrations.py        upgrades the database automatically on start
  backups.py           automatic backups + retention
  auth.py              login, passkeys, rate limiting, settings
  api/                 one file per feature (spending, bills, budgets, ...)
frontend/              React app
  src/pages/           one file per screen
  src/components/      shared pieces (forms, lists, charts, UI kit)
  src/styles.css       all styles; colours are tokens at the top
```

## Getting started

**Full setup guide: [INSTALL.md](INSTALL.md).** It covers installing on a
server with Docker, HTTPS and Face ID, updating, configuration, running
locally for development, and troubleshooting.

Quick version, on a Linux server with Docker and git installed:

```bash
git clone https://github.com/bparry-dev-ai/SpendU.git
cd SpendU
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" > .env
sudo mkdir -p /opt/docker/SpendU/data
docker network create proxy            # skip if you already have this network
docker compose up -d --build
docker compose exec spendu flask create-user
```

Then open `http://<server-ip>:5000` and sign in. Check the data folder and the
timezone in `docker-compose.yml` first (INSTALL.md §2.4).

## More documentation

| File | What's in it |
|---|---|
| [INSTALL.md](INSTALL.md) | Installing, updating, configuring and troubleshooting |
| [BACKUPS.md](BACKUPS.md) | Automatic backups, restoring, and VM backups with Proxmox |
| [PROJECT_NOTES.md](PROJECT_NOTES.md) | How the code works and why: database, sign-in, design decisions |
