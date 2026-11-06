# SpendU — backups, logs and restoring

SpendU is protected by two layers of backups:

| Layer | Protects against | Who runs it |
|---|---|---|
| **1. In-app backups** | a bad upgrade, a buggy feature, a bad CSV import or bulk delete | the app, automatically |
| **2. Proxmox VM backups** | the Docker VM or the disk dying | Proxmox, on a schedule you set up (§4) |

Paths used below (server):

| What | Path |
|---|---|
| Project / git repo | `/opt/spendu/SpendU` |
| Data folder (mounted into the container as `/app/data`) | `/opt/docker/SpendU/data` |
| Live database | `/opt/docker/SpendU/data/spending.db` |
| In-app backups | `/opt/docker/SpendU/data/backups/` |

---

## 1. How the in-app backups work

The app copies the database using SQLite's built-in backup API, so the copy
is consistent even while the app is in use. A plain `cp` of a busy database
can produce a corrupted copy.

| When | Filename | Deleted automatically? |
|---|---|---|
| Before every database upgrade (migration) | `spending-premigrate-YYYY-MM-DD-HHMMSS.db` | never |
| Before every CSV import | `spending-preimport-YYYY-MM-DD-HHMMSS.db` | never |
| Once a day (first request of the day) | `spending-daily-YYYY-MM-DD.db` | after 14 days, **except the newest backup** |

**Retention rule:** daily backups older than 14 days are deleted, but the
**newest backup in the folder is never deleted, however old it is**, so at
least one backup always exists.

If a migration fails, the original database is left untouched (the
migration runs in a transaction) and the container logs show the error.

Pre-migration and pre-import backups pile up slowly; delete old ones by hand
when you're confident you don't need them.

---

## 2. Reading error logs (on the Docker VM)

```bash
cd /opt/spendu/SpendU
docker compose ps                         # is it Up, or Restarting?
docker compose logs --tail 100 spendu     # last 100 lines
docker compose logs -f spendu             # follow live (Ctrl+C to stop)
docker compose logs --since 1h spendu     # only the last hour
docker compose logs spendu 2>&1 | grep -iE "error|traceback|exception"
df -h                                     # a full disk is a common hidden cause
sudo journalctl -u docker --since today   # if containers won't start at all
```

On the Proxmox host, open a backup job's log by double-clicking the task in
the **Tasks** panel at the bottom of the web UI, or from the host shell:

```bash
journalctl -u pvescheduler --since "24 hours ago"
```

---

## 3. Restoring a database backup (on the Docker VM)

```bash
# 1. See which backups exist
ls -lh /opt/docker/SpendU/data/backups/

# 2. Stop the app so nothing writes to the database
cd /opt/spendu/SpendU && docker compose stop spendu

# 3. Save the current database first, so the restore itself can be undone
sudo cp /opt/docker/SpendU/data/spending.db \
  /opt/docker/SpendU/data/backups/spending-before-restore-$(date +%F-%H%M).db

# 4. Remove leftover temp files of the old database (if they exist)
sudo rm -f /opt/docker/SpendU/data/spending.db-wal /opt/docker/SpendU/data/spending.db-shm

# 5. Copy the chosen backup into place
sudo cp /opt/docker/SpendU/data/backups/spending-daily-2026-11-03.db \
  /opt/docker/SpendU/data/spending.db

# 6. (Optional) check the restored file is healthy — should print "ok"
sudo apt install -y sqlite3     # first time only
sqlite3 /opt/docker/SpendU/data/spending.db "PRAGMA integrity_check;"

# 7. Start the app and watch the logs
docker compose start spendu && docker compose logs -f spendu
```

**Restoring a pre-migration backup because an upgrade broke things?** Roll
the code back too, otherwise the app upgrades the database again on startup:

```bash
git log --oneline -10                                  # find the last good commit
git checkout <good-commit-id> && docker compose up -d --build
# ...later, once the fix is pushed:
git checkout main && git pull origin main && docker compose up -d --build
```

---

## 4. Setting up the Proxmox VM backups (Layer 2)

### Step 1 — Choose where the backups go
They **must not** be on the same disk as the VM. Best first:

- **Proxmox Backup Server (PBS)** on another machine or spare disk —
  incremental, deduplicated, and can pull a single file (like `spending.db`)
  out of a backup.
- **A NAS share** (NFS or SMB).
- **A second physical disk** in the Proxmox host.

### Step 2 — Add the storage
Web UI: **Datacenter → Storage → Add**

- **NAS:** NFS or SMB/CIFS → server + share → **Content:** `VZDump backup file`.
- **PBS:** Proxmox Backup Server → address, datastore, credentials.
- **Second disk:** **your node → Disks → Directory → Create** → pick the disk,
  `ext4`, leave **Add Storage** ticked. ⚠️ This **erases that disk**.

NFS from the host shell (use your NAS's IP and share path):

```bash
pvesm add nfs nas-backup --server 192.168.1.50 --export /volume1/proxmox --content backup
```

### Step 3 — Install the QEMU guest agent in the Docker VM
Lets Proxmox briefly freeze disk writes during the backup so the database is
captured cleanly. Inside the Docker VM:

```bash
sudo apt install -y qemu-guest-agent && sudo systemctl enable --now qemu-guest-agent
```

In Proxmox: **the VM → Options → QEMU Guest Agent → Enabled**. Then fully
**shut down and start** the VM (a reboot from inside doesn't apply it).
Check from the host shell (use your VM ID) — no output means it works:

```bash
qm agent 100 ping
```

### Step 4 — Create the scheduled job
**Datacenter → Backup → Add**

| Field | Value |
|---|---|
| Storage | the one from Step 2 |
| Schedule | `03:00` (daily, 3 AM) |
| Selection mode | Include selected VMs → tick the Docker VM |
| Mode | Snapshot (no downtime) |
| Compression | ZSTD |
| Retention tab | Keep Daily `7`, Keep Weekly `4`, Keep Monthly `3` |
| Notifications | email on failure (if mail is configured) |

### Step 5 — Run it once now and check it
Select the job → **Run now** → double-click the task to read its log. Or:

```bash
vzdump 100 --storage nas-backup --mode snapshot --compress zstd
pvesm list nas-backup
```

### Step 6 — Test a restore (once — an untested backup isn't a backup)
**Storage → Backups** → select a backup → **Restore** → new VM ID (e.g.
`999`), tick **Unique**. Before starting it: **Hardware → Network Device →
Edit → Disconnect** (avoids an IP clash with the real VM). Start it, check
`/opt/docker/SpendU/data/spending.db` exists from the console, then remove it:

```bash
qm stop 999 && qm destroy 999
```

### Recovering from a dead VM
- **Whole VM:** **Storage → Backups** → select → **Restore** onto the original
  VM ID (overwrites it). From the host shell:
  ```bash
  qmrestore /mnt/pve/nas-backup/dump/vzdump-qemu-100-2026_11_05-03_00_00.vma.zst 100 --force
  ```
- **Just the database:** with PBS use **Backups → File Restore**, browse to
  `/opt/docker/SpendU/data/`, download `spending.db`, then follow §3. Without
  PBS, restore to a test VM (Step 6) and `scp` the file off it.

---

**Next level (optional):** an off-site copy of the Proxmox backups (another
location or cloud storage) protects against fire or theft of the server.
