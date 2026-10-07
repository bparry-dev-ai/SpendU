# SpendU — feature and design notes

Written 2026-07-03. Covers the authentication, Face ID, family-profiles, and
theme work done in the sandbox copy. Everything here is implemented and tested
but not yet deployed to the server.

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
| `DB_PATH` | no (defaults to `/app/spending.db`, the docker path) | set to `spending.db` to run locally on Windows |
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

- No rate limiting on the login endpoint. Fine while the app is only
  reachable through Tailscale; add one (e.g. Flask-Limiter) before ever
  exposing it publicly via Cloudflare.
- Session lifetime is "browser session" — closing the browser logs you out.
  Could add "remember me" via `session.permanent`.
- Bill types are shared; could become per-user like cards/categories.
- Old transactions can't be reassigned between users from the UI (SQL only).
