# SpendU v2 — Go-Live Guide

Everything to do, in order, to get v2 from this PC onto the server, working
and tested. Tick the boxes as you go. Don't skip ahead: each part makes the
next one safe.

| Part | Where | What | Time |
|---|---|---|---|
| 1 | PC (VS Code) | Set up and test v2 locally | 30–45 min |
| 2 | PC (VS Code) | Commit and push to GitHub | 10 min |
| 3 | Proxmox | Back up the Docker VM **before touching anything** | 15–30 min |
| 4 | Docker VM | Update the VM (Ubuntu + Docker) | 20–40 min |
| 5 | Docker VM | Deploy v2 | 15 min |
| 6 | Phone | Test everything on the live app | 30 min |
| 7 | Phone/PC | First-time setup of your real data | 20 min |
| 8 | — | Your normal workflow from now on | — |
| 9 | — | Troubleshooting and rollback | as needed |

> **Terminal note:** in VS Code open the terminal with **Ctrl + `**. Part 1
> and 2 commands are written for **PowerShell** (VS Code's default on
> Windows). Parts 3–5 run on the server over SSH (Linux/bash).

---

## ▶ Where you left off (5 Nov 2026)

Part 1 is done except the two items below. Do these first, then start
**Part 2**.

**Start the app again** (VS Code terminal, in the SpendU folder):
```powershell
.\venv\Scripts\Activate.ps1
python app.py
```
(No need to rebuild the frontend — it's already built with today's fixes.)

### A. Quick phone check (5 min)
On your phone, turn **Tailscale on**, open **http://100.77.206.100:5000**
and sign in with your **test** login (not your real one). Add one
transaction and check:
- [ ] Tapping **Amount** brings up the number keypad.
- [ ] The keyboard doesn't hide the **Add** button (scrolling a little is fine).
- [ ] Type `Tes` in Merchant → **tap Tesco** in the list → Groceries is picked.
- [ ] The **date** picker opens and you can change the date.
- [ ] Open the transaction in Activity → **Delete** works with two taps.

If the page won't load on the phone: Start menu → **Allow an app through
Windows Firewall** → **Change settings** → tick **Private** for Python → OK.
(Face ID won't work at this address — that's expected; it's tested in Part 6.)

### B. CSV export / import (5 min, PC or phone)
- [ ] **Activity → Export CSV** downloads a file and it opens in Excel.
- [ ] *(Optional)* **Import CSV** → pick a card → choose any bank CSV you have
  → **Preview**. Check purchases look normal and refunds are green. You don't
  have to click Import.

> Already checked automatically on 5 Nov: export, AMEX and Apple Card import,
> duplicate detection and the pre-import backup all work. Navy Federal and
> Keesler still need real files — that's Part 7.4.

When A and B are ticked: **Ctrl + C** to stop the app, then go to Part 2.

---

## Part 1 — Set up and test v2 on this PC

### 1.1 Open the project
1. Open VS Code → **File → Open Folder** →
   `C:\Users\bparr\OneDrive\Desktop\VSCode\Projects\SpendU`
2. Open a terminal (**Ctrl + `**).
3. Confirm you're on the v2 branch:
   ```powershell
   git status
   ```
   - [ ] First line says `On branch v2-revamp`. If it says `main`, run
     `git checkout v2-revamp`.

### 1.2 Create a Python virtual environment (one time)
Keeps SpendU's packages separate from the rest of your PC.
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```
- If you get *"running scripts is disabled on this system"*, run this once,
  then repeat the Activate line:
  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
  ```
- [ ] Your prompt now starts with `(venv)`. **Every time you open a new
  terminal for SpendU, run `.\venv\Scripts\Activate.ps1` first.**

Install the Python packages:
```powershell
pip install -r requirements.txt
```

### 1.3 Install the frontend packages (one time)
```powershell
cd frontend
npm install
cd ..
```

### 1.4 Check your local `.env`
Open `.env` in VS Code (it's in the project folder, never committed). It
should contain:
```
SECRET_KEY=<a long random string>
DB_PATH=spending.db
FLASK_DEBUG=1
```
- [ ] `SECRET_KEY` and `DB_PATH=spending.db` are already there — just add
  the `FLASK_DEBUG=1` line.

> The `spending.db` on this PC is an old, empty test database. v2 upgrades it
> automatically the first time it starts (and backs it up first into a new
> `backups\` folder). Your real data on the server is not involved.

### 1.5 Create a local test login
```powershell
flask create-user
```
Enter a username (e.g. `test`) and a password (8+ characters).

### 1.6 Build the frontend and start the app
```powershell
cd frontend
npm run build
cd ..
python app.py
```
- [ ] You see `[migrate] database is at version 2` and `Running on http://...:5000`.
- Open **http://localhost:5000** in your browser.
- To stop the app later: click the terminal and press **Ctrl + C**.

### 1.7 Local test checklist
Do these in order (start with an empty database, so you're building it up):

- [ ] Sign in with the test login. Tick "Keep me signed in".
- [ ] Home shows the welcome card.
- [ ] Tap **Add transaction** → type an amount → type a merchant (e.g.
  `Tesco`) → tap **+ New** under Category and create `Groceries` → tap
  **+ New** under Card and create `AMEX` → **Add**. A green "Spending added"
  message appears.
- [ ] Add a second transaction: type the amount, then type `Tesco` again.
  Without touching Category, **Groceries** should get selected by itself
  (whether you type the full name or tap Tesco in the list that drops down).
- [ ] Add a **Refund** (switch the top tab to Refund). It shows in green with
  a `+`.
- [ ] Go to **Activity** → tap a transaction → change the amount → **Save**.
  Then open it again and **Delete** (tap twice to confirm).
- [ ] **Bills** → **New bill** → `Rent`, amount, due day, card → **Add bill**.
  It appears on the checklist → **Mark paid** → it turns to Paid.
- [ ] **Budgets** → **New budget** → Groceries, $300 → shows a progress bar.
- [ ] **Subscriptions** → **New** → `Netflix`, $15.49, monthly, next charge =
  **today** → it appears under "Waiting for you to confirm" (also on Home) →
  tap the ✓ → it's added to spending.
- [ ] **Insights** → check the Breakdown, Trends and Calendar tabs load.
- [ ] **Import CSV** → if you have a statement CSV from any of your banks,
  try a preview (you don't have to import). See Part 7.3 for how to export one.
- [ ] **Settings** → switch Appearance to Dark and back. Check Timezone shows
  `Europe/London`.
- [ ] **Activity → Export CSV** downloads a file.
- [ ] Make the browser window narrow (or press **F12 → phone icon**) — the
  bottom tab bar with the **+** button should appear.
- [ ] Sign out (Settings → bottom), sign back in.

When done: **Ctrl + C** in the terminal to stop the app.

> **Optional — editing the look?** Run the app the "live reload" way: one
> terminal runs `python app.py`, a second terminal runs
> `cd frontend; npm run dev`, and you open **http://localhost:5173**. Saving a
> file updates the page instantly.

---

## Part 2 — Commit and push to GitHub

### 2.1 Review what's changing
In VS Code click the **Source Control** icon (left bar, the branch symbol).
You'll see the new `spendu/`, `frontend/`, `BACKUPS.md`, this guide, etc.,
and the old `templates/` and `static/` as deleted. That's expected.

- [ ] Make sure **none** of these appear in the list: `.env`, `spending.db`,
  `venv/`, `frontend/node_modules/`, `frontend/dist/`, `backups/`. (They're
  in `.gitignore`; if one shows up, stop and ask me.)

### 2.2 Commit on the v2 branch
```powershell
git add -A
git commit -m "SpendU v2: Flask API + React app, bills checklist, budgets, subscriptions, CSV import, backups"
git push -u origin v2-revamp
```

### 2.3 Merge into main (the server deploys `main`)
```powershell
git checkout main
git pull origin main
git merge v2-revamp
git push origin main
git checkout v2-revamp
```
- [ ] On github.com/bparry-dev-ai/SpendU the `main` branch now shows the
  `spendu` and `frontend` folders.

> Prefer reviewing on GitHub? Instead of 2.3, open a Pull Request from
> `v2-revamp` into `main` on the website and click **Merge**.

---

## Part 3 — Back up the Docker VM first (Proxmox)

You're about to update the VM **and** upgrade the database. Take a full VM
backup first so you can undo *anything*.

### 3.1 Quick option: a snapshot (fastest, do this at minimum)
Proxmox web UI → click your **Docker VM** → **Snapshots** → **Take Snapshot**
→ Name: `before-v2` → tick **Include RAM** off → **Take Snapshot**.

- [ ] Snapshot `before-v2` is listed.

> A snapshot lives on the same disk as the VM, so it protects against
> mistakes, not disk failure. Delete it once everything has been working for
> a week (**Snapshots → before-v2 → Remove**) — old snapshots slowly eat disk
> space.

### 3.2 Better option: set up the scheduled backups now
Follow **BACKUPS.md → section 4 (Steps 1–5)** to set up the nightly Proxmox
backup to separate storage, then click **Run now** once.
- [ ] A backup of the Docker VM finished successfully (Task log says `TASK OK`).

(If you don't have a second disk or NAS ready yet, do 3.1 tonight and 3.2
another day — but do get to it.)

---

## Part 4 — Bring the Docker VM up to date

SSH into the Docker VM (from VS Code's terminal or PowerShell):
```powershell
ssh <your-user>@<docker-vm-ip>
```
Everything below runs **on the VM**.

### 4.1 Look around first
```bash
lsb_release -a          # Ubuntu version
uptime                  # how long since the last reboot
df -h /                 # disk space — "Use%" should be under ~80%
docker --version
docker compose version  # must print a version (the v2 "docker compose" plugin)
docker ps               # what's running right now — note the names
```
Write down what `docker ps` shows so you can confirm everything comes back
after the updates.

- [ ] **Ubuntu version:** `24.04` or `22.04` → fine, continue. `20.04` or
  older → it's out of support; finish this guide first, then see
  **4.7 (optional)**.
- [ ] **Disk:** if `/` is over ~85% full, do step 4.5 (cleanup) *before* 4.2.

### 4.2 Update Ubuntu packages
```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt autoremove -y
```
If a purple screen asks which services to restart, accept the defaults
(press **Enter**). If it asks about keeping a modified config file, choose
**keep the local version currently installed**.

### 4.3 Make sure Docker itself got updated
Check how Docker was installed:
```bash
apt list --installed 2>/dev/null | grep -E "docker-ce|docker.io|containerd"
snap list 2>/dev/null | grep docker
```
- `docker-ce` listed → installed from Docker's official repo → step 4.2
  already updated it. ✅
- `docker.io` listed → Ubuntu's package → also updated by 4.2. ✅ (Make sure
  `docker compose version` works; if not: `sudo apt install docker-compose-v2`.)
- Only the **snap** shows Docker → update it with `sudo snap refresh docker`.

```bash
docker --version
docker compose version
```

### 4.4 Reboot if needed
```bash
ls /var/run/reboot-required 2>/dev/null && echo "REBOOT NEEDED" || echo "no reboot needed"
```
If it says REBOOT NEEDED:
```bash
sudo reboot
```
Wait a minute, SSH back in, then:
```bash
docker ps
```
- [ ] The same containers as in 4.1 are running again (`restart:
  unless-stopped` brings them back). If one isn't, `cd` to its folder and run
  `docker compose up -d`.
- [ ] SpendU v1 still opens on your phone (sanity check before changing it).

### 4.5 Clean up old Docker leftovers (safe commands only)
```bash
docker system df          # see what's using space
docker image prune -f     # removes dangling (unused, untagged) images only
docker builder prune -f   # removes old build cache
```
> ⚠️ Don't run `docker system prune -a --volumes` — that can delete images
> and volumes other containers still need.

### 4.6 Small health checks
```bash
timedatectl               # "System clock synchronized: yes" — correct time matters for due dates & backups
sudo systemctl status qemu-guest-agent --no-pager   # needed for clean Proxmox backups (BACKUPS.md 4, step 3)
```
If the guest agent isn't installed:
```bash
sudo apt install -y qemu-guest-agent && sudo systemctl enable --now qemu-guest-agent
```
(then enable it in Proxmox: VM → Options → QEMU Guest Agent → Enabled, and
fully shut down + start the VM once when convenient.)

### 4.7 (Optional, another day) Ubuntu 20.04 or older
Only if 4.1 showed 20.04 or older. Take a fresh Proxmox backup first, then:
```bash
sudo do-release-upgrade
```
This goes up one version at a time (20.04 → 22.04, then run again for
24.04). It takes a while and asks questions — do it when you have an hour,
not before bed.

---

## Part 5 — Deploy v2 on the Docker VM

Still SSH'd into the VM.

### 5.1 Go to the project and check it's clean
```bash
cd /opt/spendu/SpendU
git status
```
- [ ] It says `nothing to commit, working tree clean` (untracked `.env` is
  fine). If it lists **modified** files (e.g. you once edited
  `docker-compose.yml` on the server), see what changed with `git diff`,
  write down anything important (like a `SECRET_KEY` line), then run
  `git stash` to set the changes aside.

### 5.2 Check the SECRET_KEY is in `.env`
```bash
grep -c SECRET_KEY .env
```
- [ ] Prints `1`. (If it prints `0` or "No such file", the key was set
  somewhere else — find it before continuing, or create `.env` with
  `SECRET_KEY=` plus the **same** value as before. A new value just logs
  everyone out; nothing else breaks.)

### 5.3 Extra safety copy of the database
```bash
sudo cp /opt/docker/SpendU/data/spending.db /opt/docker/SpendU/data/spending-before-v2.db
ls -lh /opt/docker/SpendU/data/
```
- [ ] Both `spending.db` and `spending-before-v2.db` are listed with the same size.

### 5.4 Pull the new code
```bash
git pull origin main
ls
```
- [ ] You see `spendu`, `frontend`, `BACKUPS.md`, `GO_LIVE_GUIDE.md`.

### 5.5 Build and start v2
```bash
docker compose up -d --build
```
The first build takes several minutes (it downloads Node and builds the
React app inside Docker). Then watch the logs:
```bash
docker compose logs -f spendu
```
- [ ] You see these lines (Ctrl + C to stop watching):
  ```
  [backup] created /app/data/backups/spending-premigrate-....db
  [migrate] applying migration 1 ...
  [migrate] applying migration 2 ...
  [migrate] database is at version 2
  Listening at: http://0.0.0.0:5000
  ```
- [ ] `docker compose ps` shows `spendu` as **Up** (not "Restarting").
- [ ] The automatic backup exists:
  ```bash
  ls -lh /opt/docker/SpendU/data/backups/
  ```

### 5.6 Clean up the old image
```bash
docker image prune -f
```

If anything in Part 5 fails, go to **Part 9**.

---

## Part 6 — Test the live app (on your phone)

Open SpendU at your usual address (the Tailscale/HTTPS one) and **pull down
to refresh** (or close and reopen the tab) so the phone loads the new app.

### Core
- [ ] Password sign-in works, with "Keep me signed in" ticked.
- [ ] **Face ID**: sign out → "Sign in with Face ID / Passkey" works with the
  passkey you already had (same domain, so no re-enrolling).
- [ ] Home shows your real numbers. **Spent in November** should match what
  you'd expect from your v1 data.
- [ ] **Activity** lists your old transactions (old ones have no merchant —
  they show the category name instead; that's normal).
- [ ] Search and the **Bills** filter on Activity show your old bill payments.

### Make changes (you can delete these test entries afterwards)
- [ ] Add a purchase, edit it, delete it.
- [ ] Add a refund.
- [ ] Mark a bill paid (after Part 7.1), then on the bill tap **Edit → Remove
  payment** if it was just a test.

### Family
- [ ] Sign in as the second user (on their phone or yours): they see **only
  their own** transactions, but the same bills checklist and family totals.

### Server side
- [ ] Tomorrow, check a daily backup appeared:
  ```bash
  ls -lh /opt/docker/SpendU/data/backups/
  ```
  (`spending-daily-YYYY-MM-DD.db` — one is made on the first visit each day.)

---

## Part 7 — First-time setup with your real data

### 7.1 Put your old bills on the checklist
**Bills** → card **"Finish setting up"** → for each bill tap **Set due day**
→ fill in **Usual amount**, **Due day**, **How often** (monthly/yearly),
**Usually paid with** → **Save**. Repeat for each. Bills already paid this
month show as **Paid** straight away.

Add any bills you never entered before with **New bill**.

### 7.2 Tidy cards and categories
**Settings → Cards / Categories**: tap a name to rename it, pick a colour,
and give categories an emoji (🛒 🍔 ⛽ …). Cards you no longer use: tap the
archive icon (hides them from pickers, keeps history).

### 7.3 Budgets and subscriptions
- **Budgets → New budget**: a few categories you want to keep an eye on, and
  optionally "All spending". Family budgets (e.g. Groceries) count both of you.
- **Subscriptions → New**: Netflix, Spotify, gym, etc. with their next charge
  date.

### 7.4 Try a CSV import from each bank
On each bank's website, export recent transactions as **CSV**:
- **Apple Card**: Wallet app → Apple Card → Card Balance → a monthly
  statement → **Export Transactions** → CSV.
- **AMEX**: americanexpress.com → Statements & Activity → Download → CSV.
- **Navy Federal**: Online banking → the account → Download/Export → CSV.
- **Keesler**: Online banking → the account → Export/Download → CSV.

Then **Import CSV** → pick the matching card → choose the file → **Preview**.
Check the amounts look right (purchases plain, refunds green), set
categories, **Import**.

- [ ] **Please send me the first line (column headers) of the Navy Federal
  and Keesler files** — just the header row, no transactions. Those two
  presets are best guesses and I'll make them exact.

> Tip: if an import is wrong, a `spending-preimport-...` backup was taken
> right before it — see BACKUPS.md §3 to roll back.

### 7.5 Change the timezone later
When you move back to the US: **Settings → Timezone** → pick your new one.
(Each person sets their own.)

---

## Part 8 — Your normal workflow from now on

**Making a change:**
1. PC: open VS Code → terminal → `.\venv\Scripts\Activate.ps1`
2. Make the change, test it locally (`cd frontend; npm run build; cd ..; python app.py`).
3. Commit and push:
   ```powershell
   git add -A
   git commit -m "Describe the change"
   git push origin main
   ```
4. Server:
   ```bash
   cd /opt/spendu/SpendU
   git pull origin main
   docker compose up -d --build
   docker compose logs -f spendu
   ```

**Monthly VM maintenance (10 minutes):**
```bash
sudo apt update && sudo apt full-upgrade -y && sudo apt autoremove -y
ls /var/run/reboot-required 2>/dev/null && sudo reboot
docker image prune -f
df -h /
ls -lh /opt/docker/SpendU/data/backups/
```
And glance at Proxmox → Datacenter → Backup / Tasks to confirm the nightly
backups say OK.

---

## Part 9 — Troubleshooting and rollback

| Symptom | Fix |
|---|---|
| `docker compose ps` shows **Restarting** | `docker compose logs --tail 80 spendu` and read the last error. |
| Log says `SECRET_KEY is not set` | `.env` is missing in `/opt/spendu/SpendU` or has no `SECRET_KEY` line (Part 5.2), then `docker compose up -d --build`. |
| Log says `migration ... FAILED` | The database was left unchanged. Copy the error and send it to me. The app won't start until fixed — do the rollback below if you need v1 back now. |
| Page says *"Frontend not built"* | The Node build stage didn't run — `docker compose build --no-cache && docker compose up -d`. |
| `unable to open database file` | Check the folder: `ls -l /opt/docker/SpendU/data/`. The compose file now mounts the **folder**, so `spending.db` must be inside it. |
| Phone still shows the old app | Close the tab completely and reopen, or clear the site data in browser settings. |
| `git pull` says your local changes would be overwritten | `git stash`, then `git pull origin main` again (Part 5.1). |
| Build fails with `no space left on device` | Part 4.5 cleanup, then try again. |
| Face ID button missing / fails | It needs the HTTPS address (Tailscale), not the plain `http://IP:5000` one. Password login always works. |

### Rollback to v1 (if you need the old app back tonight)
```bash
cd /opt/spendu/SpendU
docker compose down
git log --oneline -5                     # find the commit BEFORE the v2 merge (e.g. 13fc96c)
git checkout 13fc96c
sudo cp /opt/docker/SpendU/data/spending-before-v2.db /opt/docker/SpendU/data/spending.db
sudo rm -f /opt/docker/SpendU/data/spending.db-wal /opt/docker/SpendU/data/spending.db-shm
docker compose up -d --build
```
This puts back the v1 code **and** the database exactly as it was before
Part 5 (anything entered in v2 since is lost). To go forward again later:
`git checkout main`, then Part 5.4–5.5.

**Nuclear option:** Proxmox → Docker VM → Snapshots → `before-v2` →
**Rollback** puts the whole VM back to how it was in Part 3.

---

*When you're done, send me: the Navy Federal and Keesler CSV header lines,
and anything that didn't behave as described above.*
