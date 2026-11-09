# SpendU — feature and design notes

## Budget Planner (2026-11-08) — replaces the Budgets page

- **Page:** `/planner` (`frontend/src/pages/Planner.jsx`). **API:** `/api/planner`
  (`spendu/api/planner.py`; its docstring explains every rule). `/budgets` redirects here.
- **Migration 3** adds `plans` (one per person, plus one household plan with
  `owner_user_id` NULL; holds `income` and an optional `overall_cap`) and
  `plan_lines` (group needs/wants/savings; kind category/bill/subscription/custom).
  Old `budgets` rows are copied in: personal → your plan, family → household,
  "All spending" → `overall_cap`. The `budgets` table itself is left untouched.
- **Tracking:** category lines match spending by category **name** (household = everyone's);
  bill lines use payments by `bill_month`; subscription lines use confirmed charges.
  Charges from a subscription that has its own line are excluded from category lines,
  so nothing counts twice. Custom (savings) lines are planned only.
- **Auto lines:** every active bill goes into the household plan. Your personal plan
  gets bills set to your card or last paid by you, plus your active subscriptions.
  Removing an auto line only hides it (`hidden = 1`). Bill/sub lines with `amount`
  NULL follow the usual amount (yearly bills ÷ 12).
- **Live:** everything is recalculated on each request, and the page refetches after any
  change, so a new transaction or bill payment shows up straight away.
- **History** = average of the last N complete months (1/3/6/12, default 3), or fewer
  if there isn't that much history yet.
- **Home's "Budget" card** lists category lines (and overall caps) from both plans as
  monthly limits, worst first.

## v2 (2026-11-04): Flask API + React rewrite

**What changed**
- The Jinja templates are replaced by a React app (`frontend/`). Flask is now
  a JSON API under `/api/...` (`spendu/`), and it also serves the built React
  files. The old `templates/` and `static/` folders were removed; they are
  still in git history.
- Production runs under **gunicorn** with debug off. Locally, `python app.py`
  only turns on debug when `FLASK_DEBUG=1` is set.
- Logins, passkeys and family profiles (§1–3 below) work exactly as before.

**Database: upgraded in place, nothing removed**
- `spendu/migrations.py` keeps a version number in `PRAGMA user_version`.
  Migration 1 is the v1.2 schema (a no-op on the live server). Migration 2
  only **adds** columns and tables:
  - `spending`: merchant, notes, recurring_id, import_hash, created_at.
    **Refunds are stored as negative amounts**, so `SUM(amount)` is always
    net spending.
  - `bills` (payments): bill_month (which month's bill it pays, backfilled
    from the date), notes.
  - `bill_info`: amount, due_day, frequency (monthly/yearly), due_month,
    card_id (default card), autopay, active, start_month, notes. Old bills
    have no due_day, so they show under "Finish setting up" until you give
    them one.
  - `card_info` / `category_info`: color, archived (plus icon for categories;
    import_preset/import_mapping for cards).
  - `users`: timezone.
  - New tables: `budgets`, `recurring` (subscriptions), `login_attempts`.
- A backup is taken before migrating, and each migration runs in a
  transaction. See BACKUPS.md.

**Feature rules worth remembering**
- A bill counts as paid for a month when a payment with that `bill_month`
  exists. Bills are shared family-wide; payments show who paid, but never
  the other person's card.
- Budgets: personal budgets count your own spending, family budgets count
  everyone's. Both match categories **by name**, since each person has their
  own category list, and renaming a category updates your personal budgets.
  Bills don't count toward budgets.
- Subscriptions never add spending by themselves. When one is due it stays
  pending until you Confirm it (which logs it and can update the price) or
  Skip it.
- CSV import: presets live in `spendu/api/imports.py` (`PRESETS`). Rows
  already imported are recognised by a fingerprint (`import_hash`), and
  manual entries with the same card and amount within ±3 days are flagged
  as possible duplicates. Card payments and money-in are unticked by
  default. The Navy Federal and Keesler presets are best guesses; if a real
  export doesn't map correctly, fix the column names in `PRESETS`.
- "Today" uses each user's timezone (Settings), falling back to
  `DEFAULT_TIMEZONE`, so moving back to the US is a one-tap change.

**Security additions**
- Login rate limit: after 5 failures per username or 20 per IP within 15
  minutes, further attempts are refused until the window passes. Set
  `TRUST_PROXY=1` behind a reverse proxy so the real IP is used.
- "Keep me signed in" lasts 30 days, and is always on for Face ID sign-ins.
- CSRF: every change-making API request must carry the `X-SpendU: 1` header,
  which other websites can't add. This is on top of `SameSite=Lax` cookies.

Sections 1–5 below are still accurate. Section 6 (the sage theme) is
replaced by the v2 design: tokens are at the top of
`frontend/src/styles.css`, with light and dark modes. For section 8 (local
development), see README.md.

---

*Notes from 2026-07-03 (v1.2), covering the authentication, Face ID and
family-profiles work:*

---

## 1. Login and accounts

Every page and action now requires signing in. Anonymous visitors are
redirected to `/login`.

**How accounts work**
- Accounts are created only from the command line — there is no public
  registration page:
  ```
  flask create-user            # local
  docker compose exec <service> flask create-user   
      # under /opt/docker/SpendU/on the server
  ```
  It prompts for a username and a password (minimum 8 characters). Running it
  again with the same username resets that user's password — this is the
  "forgot password" recovery path.
- Passwords are stored as salted pbkdf2 hashes (Werkzeug), never plaintext.
- Login failures show the same generic message whether the username or the
  password was wrong, so usernames can't be discovered by guessing.

**Sessions**
- Flask sessions signed with `SECRET_KEY` (see §5). Cookies are `HttpOnly`
  (JavaScript can't read them) and `SameSite=Lax` (blocks cross-site POST
  forgery on the add/delete endpoints).
- Logout is the 🔒 button on the homepage.

## 2. Face ID / passkeys (WebAuthn)

Passwordless sign-in using the phone's biometrics.

**Using it**
1. Log in with your password once, tap **Add Face ID / Passkey** on the
   homepage, and approve the Face ID prompt.
2. From then on the login screen shows **Sign in with Face ID / Passkey**.
3. Each user enrolls independently, per device. Password login always remains
   as fallback.

**Requirements and behavior**
- Only activates over **HTTPS with a real domain** (browser rule, not ours).
  Works via `tailscale serve` or Cloudflare Tunnel; never on a plain-HTTP IP
  address. The buttons hide themselves on unsupported browsers.
- Biometric verification is required server-side (`user_verification:
  required`) — merely possessing the phone is not enough.
- Passkeys are bound to the domain. If the app moves to a different domain
  later, everyone re-enrolls once (old entries in the `passkeys` table can be
  deleted).
- Behind a proxy/tunnel that terminates HTTPS (e.g. Cloudflare Tunnel), set
  `RP_ORIGIN=https://yourdomain.com` in the docker environment because Flask
  sees plain HTTP internally. `RP_ID` can also be overridden if ever needed.
  With `tailscale serve` no configuration is required.

## 3. Family profiles

Two (or more) users share the app; spending is private per person, totals are
shared.

- Every spending/bill entry is stamped with the logged-in user.
- **Homepage**: your weekly total (big) plus the family weekly total (below
  the divider). Each user sees their own number; nobody sees the other's.
- **Analytics**: tables list only your own transactions; the totals line
  shows "Your N-day total · Family: $X". Delete buttons only work on your
  own rows (enforced in SQL, not just hidden).
- **Cards and categories are per-user**: dropdowns, "+" manage panels, and
  the analytics card filter each show only your own. The same name may exist
  in both users' lists ("Groceries" for both), but duplicates within one
  user's list are blocked.
- **Bill types are shared** family-wide (deliberate — change later if wanted).
- Privacy note: this is privacy *between profiles in the app*. Whoever
  administers the server can always open the database file directly.

## 4. Database schema and automatic migration

New/changed tables (see `schema.sql` for full definitions):

| Table | Change |
|---|---|
| `users` | new — user_id, username, password_hash |
| `passkeys` | new — WebAuthn credentials per user |
| `spending`, `bills` | added `user_id` (owner) |
| `card_info`, `category_info` | added `user_id`; name unique **per user** instead of globally |
| `bill_info` | unchanged (shared) |

**Migration is automatic.** `migrate_family_columns()` in `app.py` runs at
every startup and after each `create-user`. It:
1. Adds missing `user_id` columns to `spending`/`bills`.
2. Rebuilds `card_info`/`category_info` once (the old global UNIQUE(name)
   constraint can't be altered in place), preserving row ids so existing
   transactions stay correctly linked.
3. Assigns any unowned rows to the **earliest-created user**.

⚠ **Because of step 3, account creation order matters when deploying: create
the primary account (whoever owns the existing history) FIRST, then the
second account.**

## 5. Configuration (.env / docker environment)

| Variable | Required | Purpose |
|---|---|---|
| `SECRET_KEY` | yes — app refuses to start without it | signs session cookies; generate with `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DB_PATH` | no (v2 default `/app/data/spending.db`; docker-compose sets it) | set to `spending.db` to run locally on Windows |
| `DEFAULT_TIMEZONE` | no (falls back to `TZ`, then Europe/London) | timezone for users who haven't picked one in Settings |
| `TRUST_PROXY` | no | `1` behind a reverse proxy, so login rate limiting sees real visitor IPs |
| `FLASK_DEBUG` | no | `1` locally for auto-reload; never on the server |
| `RP_ORIGIN` | only behind Cloudflare Tunnel / HTTPS-terminating proxy | the exact origin browsers see, e.g. `https://spendu.example.com` |
| `RP_ID` | rarely | overrides the passkey domain if auto-detection is wrong |

Locally these live in `.env` (gitignored — never commit it; each environment
generates its own `SECRET_KEY`). On the server, put them in the docker
environment (compose `environment:` block or an env file next to the
compose file).

New dependency: `webauthn==3.0.0` in `requirements.txt` — picked up by the
normal `docker compose build`.

## 6. Theme

Sage/leaf design replacing the neon "circuit board" theme.

**Palette** (design tokens in `base.html` `:root` — edit values there and
every page follows):

| Token | Value | Used for |
|---|---|---|
| `--bg-sage` | `#A3B18A` | page background |
| `--leaf` | `#C5D2B2` | leaf print accents |
| `--card-bg` | `#f7e6d5` | cards and panels |
| `--accent` | `#826B5C` | buttons, borders, focus rings |
| `--terracotta` | `#B06A5B` | delete buttons, amounts, errors |
| `--text-main` | `#4F5148` | body text |
| `--text-muted2` | `#77796F` | secondary text |
| `--logo-tile` | `#899ABE` | the "S" tile |
| `--logo-letter` | `#ECE3DF` | the "S" letter |
| `--wordmark` | `#F8EDEB` | the "SpendU" wordmark, text on accent buttons |

(Values above reflect the latest hand-tuned edits; the legacy variable names
lower in `:root` — `--glass`, `--accent-cyan`, etc. — are kept mapped onto the
new palette so older page styles keep working. If you change `--card-bg`,
also change `--glass` to match: it feeds the Analytics tables.)

**Fonts** (loaded from Google Fonts in `base.html`)
- *Satisfy* — logo "S" and "SpendU" wordmark, and the login title. Nothing else.
- *Quicksand* — all other text, weights 400–700.

**Leaf background** — `static/leaves.svg`, a hand-drawn sponge-paint leaf
pattern tiled at 700×700 via the `.leaf-bg` rule in `base.html`. Edit the SVG
to change leaf shapes/density; edit `opacity` values in it to fade prints in
or out.

## 7. Deployment checklist (first deploy of all this)

1. Push to GitHub, SSH to the server, `git pull origin main` in
   `/opt/spendu/SpendU`.
2. Add `SECRET_KEY` to the docker environment (**required** — container will
   not start without it).
3. `docker compose build && docker compose up -d`.
4. `docker compose exec <service> flask create-user` — **your account first**
   (adopts all existing history), then run again for the second user.
5. Verify password login works.
6. Set up Tailscale for HTTPS (`tailscale serve --bg 5000` or per its docs),
   then enroll Face ID from each phone.
7. `docker compose logs -f` to watch for errors, as usual.

## 8. Local development on Windows

```
cd <project folder>
flask create-user     # first time only
python app.py         # http://localhost:5000
```
Requires a `.env` with `SECRET_KEY` and `DB_PATH=spending.db`. Passkeys can't
be tested from a phone locally; everything else can.

## 9. Known limitations / future ideas

- ~~No rate limiting on the login endpoint.~~ Added in v2.
- ~~Session lifetime is "browser session".~~ v2 adds a 30-day "remember me".
- Bill types are shared; could become per-user like cards/categories.
- Old transactions can't be reassigned between users from the UI (SQL only).
