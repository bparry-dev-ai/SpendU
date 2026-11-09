# Installing SpendU

A complete guide to running your own copy of SpendU: on a server with Docker
(recommended), or on your own computer for development.

**Contents**
1. [What you need](#1-what-you-need)
2. [Install on a server with Docker](#2-install-on-a-server-with-docker)
3. [HTTPS and Face ID / passkeys](#3-https-and-face-id--passkeys)
4. [Updating](#4-updating)
5. [Backups](#5-backups)
6. [Configuration reference](#6-configuration-reference)
7. [Running locally for development](#7-running-locally-for-development)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. What you need

**For a server install**
- A Linux machine or VM (Ubuntu 22.04 / 24.04 LTS works well; a Raspberry Pi
  4/5 is fine). 1 GB RAM and a few GB of disk are plenty.
- **Docker Engine** with the **Compose plugin** (`docker compose version`
  must work). Install guide: https://docs.docker.com/engine/install/
- **git** (`sudo apt install git`).
- For Face ID / passkeys and installing on phones: an **HTTPS** address
  (section 3). Password sign-in works without it.

**For local development:** Python 3.12+, Node.js 20+ (with npm) and git.

---

## 2. Install on a server with Docker

This guide keeps the code in `/opt/spendu/SpendU` and the database in
`/opt/docker/SpendU/data`. You can use other folders: just keep them
consistent with `docker-compose.yml`.

### 2.1 Get the code
```bash
sudo mkdir -p /opt/spendu
sudo chown $USER /opt/spendu
cd /opt/spendu
git clone https://github.com/bparry-dev-ai/SpendU.git
cd SpendU
```

### 2.2 Create the `.env` file (your secret key)
The app refuses to start without a `SECRET_KEY`. It signs the login cookies,
so keep it secret and never commit it (`.env` is already in `.gitignore`).

```bash
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" > .env
cat .env        # one line: SECRET_KEY=<64 random characters>
```

> `.env` is copied into the Docker image when it's built, so after changing
> it, rebuild with `docker compose up -d --build` (a plain restart won't pick
> it up).

### 2.3 Create the data folder
The database and its automatic backups live **outside** the container, so they
survive rebuilds:
```bash
sudo mkdir -p /opt/docker/SpendU/data
```
The database file is created automatically on first start.

### 2.4 Check `docker-compose.yml`
Open it (`nano docker-compose.yml`) and check three things:

1. **Data folder:** the left side of `volumes:` must be the folder from 2.3:
   ```yaml
   volumes:
     - /opt/docker/SpendU/data:/app/data
   ```
2. **Timezone:** `TZ` and `DEFAULT_TIMEZONE` default to `Europe/London`.
   Change both to yours, e.g. `America/Chicago` (list:
   https://en.wikipedia.org/wiki/List_of_tz_database_time_zones). Each person
   can also pick their own timezone later in **Settings**.
3. **The `proxy` network:** the compose file joins an existing Docker network
   called `proxy` (for a reverse proxy such as nginx in its own container).
   - **No reverse proxy?** Create the network once so it exists:
     ```bash
     docker network create proxy
     ```
     (Or delete the `networks:` sections from the file.)
   - **Already run a reverse proxy in Docker?** Change `proxy` to the name of
     its network, so it can reach SpendU at `http://spendu:5000`.

### 2.5 Build and start
```bash
docker compose up -d --build
```
The first build takes a few minutes (it builds the React frontend with Node,
then installs the Python app). Watch it start:
```bash
docker compose logs -f spendu
```
You should see:
```
[migrate] applying migration 1 ...
...
[migrate] database is at version N
Listening at: http://0.0.0.0:5000
```
Press **Ctrl + C** to stop watching (the app keeps running). Check it's up:
```bash
docker compose ps        # spendu: "Up", not "Restarting"
```
`restart: unless-stopped` in the compose file starts it again automatically
after a reboot.

### 2.6 Create the logins
There's no public sign-up page. Accounts are created on the server:
```bash
docker compose exec spendu flask create-user
```
Enter a username and a password (8+ characters). Repeat for each person.

> **Order matters if you're importing old v1 data:** the **first** account
> created takes ownership of any existing history. Create the main person's
> account first.

Running the same command with an **existing** username resets that person's
password (keeping their data). That's the "forgot password" fix.

### 2.7 Open it
In a browser on the same network: **http://\<server-ip\>:5000**. Sign in, then:
- **Settings**: pick your timezone and theme, and add your cards and categories.
- **Bills, Planner, Subscriptions**: set up your recurring money.
- **Import CSV**: load history from your bank (presets for Apple Card, American
  Express, Navy Federal and Keesler; any other bank works with column mapping).

> Don't expose port 5000 directly to the internet. Use a VPN such as Tailscale,
> or a reverse proxy with HTTPS (section 3).

---

## 3. HTTPS and Face ID / passkeys

Browsers only allow Face ID / passkeys and "install as an app" on **HTTPS**.
Pick one option.

### Option A: Tailscale (easiest, private to your devices)
1. Install Tailscale on the server and your phones
   (https://tailscale.com/download), signed in to the same account.
2. In the Tailscale admin console → **DNS**: turn on **MagicDNS** and
   **HTTPS Certificates**.
3. On the server:
   ```bash
   sudo tailscale serve --bg 5000
   tailscale serve status        # shows your https://<machine>.<tailnet>.ts.net address
   ```
4. Tell SpendU its public address. Add to `.env` (use your real address), then rebuild:
   ```bash
   echo "RP_ORIGIN=https://<machine>.<tailnet>.ts.net" >> .env
   echo "RP_ID=<machine>.<tailnet>.ts.net" >> .env
   docker compose up -d --build
   ```
Only devices signed in to your Tailscale account can open it.

### Option B: your own domain with a reverse proxy
Put SpendU behind nginx, Caddy or Traefik (with a Let's Encrypt certificate),
or behind a Cloudflare Tunnel, forwarding to `http://spendu:5000` (proxy in
Docker on the same network) or `http://<server-ip>:5000`. Then add to `.env`
and rebuild:
```
RP_ORIGIN=https://spendu.example.com
TRUST_PROXY=1
```
`TRUST_PROXY=1` makes the app trust the proxy's `X-Forwarded-*` headers, so
login rate limiting sees each visitor's real IP. Only set it when a proxy is
actually in front.

### Then, on each phone
Open the **https** address → sign in with your password → **Settings → Face
ID / passkeys → Add Face ID / passkey on this device**. Passkeys are tied to
that exact address, so always use it from then on.

---

## 4. Updating
```bash
cd /opt/spendu/SpendU
git pull
docker compose up -d --build
docker compose logs -f spendu
docker image prune -f          # remove the previous image
```
If an update changes the database, the app backs it up first
(`spending-premigrate-….db`) and upgrades it automatically on start.

---

## 5. Backups
SpendU backs up its own database every day (kept 14 days), and before every
upgrade and CSV import. Those copies sit on the same disk, so also back up the
server or the data folder somewhere else. How to check, restore and set up VM
backups: **[BACKUPS.md](BACKUPS.md)**.

Useful commands (in the SpendU folder):
```bash
docker compose exec spendu flask backup          # take a backup now
docker compose exec spendu flask list-backups    # list them
```

---

## 6. Configuration reference

Set these in `.env` (rebuild afterwards) or in the `environment:` block of
`docker-compose.yml`.

| Variable | Required | What it does |
|---|---|---|
| `SECRET_KEY` | **yes** | Signs login cookies. The app won't start without it. |
| `DB_PATH` | no | Database file. Docker: `/app/data/spending.db` (set in compose). Locally: `spending.db`. |
| `TZ` | no | The server clock's timezone (set in compose). |
| `DEFAULT_TIMEZONE` | no | Timezone for users who haven't picked one in Settings (falls back to `TZ`). |
| `RP_ORIGIN` | for HTTPS | The exact address browsers use, e.g. `https://spendu.example.com`. Needed for passkeys behind a proxy/Tailscale. |
| `RP_ID` | rarely | The passkey domain (the address without `https://`), if auto-detection gets it wrong. |
| `TRUST_PROXY` | no | `1` only when a reverse proxy is in front (real visitor IPs for rate limiting). |
| `FLASK_DEBUG` | no | `1` for local development only. **Never** on a server. |

---

## 7. Running locally for development

```bash
git clone https://github.com/bparry-dev-ai/SpendU.git
cd SpendU
python -m venv venv
```
Activate the virtual environment:
- **Windows (PowerShell):** `.\venv\Scripts\Activate.ps1`
  (if scripts are blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`)
- **macOS / Linux:** `source venv/bin/activate`

```bash
pip install -r requirements.txt
cd frontend
npm install
cd ..
```

Create `.env` in the project folder:
```
SECRET_KEY=<run: python -c "import secrets; print(secrets.token_hex(32))">
DB_PATH=spending.db
FLASK_DEBUG=1
```

Create a login, build the frontend and run:
```bash
flask create-user
cd frontend
npm run build
cd ..
python app.py
```
Open **http://localhost:5000**.

**Live reload while editing the frontend:** keep `python app.py` running, and
in a second terminal run `cd frontend` then `npm run dev`, and open
**http://localhost:5173**. Changes appear as you save.

How the code is organised and why: **[PROJECT_NOTES.md](PROJECT_NOTES.md)**.

---

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| Log: `SECRET_KEY is not set` | `.env` is missing or has no `SECRET_KEY` line (2.2), then `docker compose up -d --build`. |
| `network proxy declared as external, but could not be found` | `docker network create proxy` (2.4). |
| `unable to open database file` | The data folder from 2.3 doesn't exist, or the `volumes:` path doesn't match it. |
| `docker compose ps` shows **Restarting** | `docker compose logs --tail 80 spendu` and read the last error. |
| Page says "Frontend not built" | `docker compose build --no-cache && docker compose up -d` |
| Can't open the site from another device | Check the server's firewall allows port 5000 (`sudo ufw allow 5000/tcp` if you use ufw), or use Tailscale. |
| Face ID button missing or fails | You must be on the **HTTPS** address, and `RP_ORIGIN` must match it exactly (section 3). |
| **502 Bad Gateway** through a reverse proxy | Restart the proxy after rebuilding SpendU; it may have cached SpendU's old container address. |
| Phone still shows an old version | Close the tab completely and reopen it. |
| Build fails with `no space left on device` | `docker image prune -f && docker builder prune -f` |
| Forgot a password | `docker compose exec spendu flask create-user` with the same username (2.6). |
