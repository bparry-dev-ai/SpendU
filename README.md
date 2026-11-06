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
  credits, and bill payments.
- **Edit and delete** any transaction, plus notes on any entry.
- **Bills checklist**: set up each bill once (usual amount, due day,
  default card, monthly or yearly). Every month shows Paid, Due soon or
  Overdue, and "Mark paid" logs the payment with everything filled in.
- **Budgets**: monthly limits per category or overall, personal or
  family-wide, with an "on pace" marker.
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

## Running locally (Windows)

One-time setup:

```bash
pip install -r requirements.txt
cd frontend && npm install
```

`.env` in the project folder (never commit it):

```
SECRET_KEY=<python -c "import secrets; print(secrets.token_hex(32))">
DB_PATH=spending.db
FLASK_DEBUG=1
```

**Quick run:** build the frontend once, then let Flask serve everything on
http://localhost:5000:

```bash
cd frontend && npm run build && cd .. && python app.py
```

**While editing the frontend:** run both, then open http://localhost:5173
(it reloads instantly as you save):

```bash
python app.py
```
```bash
cd frontend && npm run dev
```

Create a login with `flask create-user`.

Deploying to the server is covered in [build_notes.txt](build_notes.txt);
design details are in [PROJECT_NOTES.md](PROJECT_NOTES.md).
