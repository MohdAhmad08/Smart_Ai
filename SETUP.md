# Manual Local Setup

Step-by-step guide to run the Manufacturing Intelligence Platform locally (without full Docker).
MySQL and RabbitMQ still run in Docker because they're painful to install natively; everything
else runs directly on your machine.

> **Two gotchas the main README misses** — both are already handled in the steps below:
> - Run the **backend on port 8000**, not 8077. The frontend has `http://localhost:8000`
>   hardcoded as its API base, so on 8077 the dashboard loads but shows no data.
> - Add **`RABBIT_MQ_HOST=localhost`** to your `.env`. The template omits it and the generator
>   has no fallback, so without it the publisher can't reach RabbitMQ.

---

## Prerequisites

- Python 3.10+
- Node.js 18+
- Docker (used only for MySQL + RabbitMQ)

---

## Step 1 — Virtual environment

From the repo root:

```bash
python -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate        # macOS / Linux
.venv\Scripts\Activate.ps1       # Windows PowerShell
.venv\Scripts\activate.bat       # Windows CMD
```

Your prompt shows `(.venv)` when it's active. Install all Python dependencies once:

```bash
pip install -r backend/requirements.txt
pip install -r ml/requirements.txt
pip install -r rabbitmq/producer/publisher/requirements.txt
```

---

## Step 2 — Create your `.env`

```bash
cp .env.example .env
```

Then **add this line** to `.env` (the template is missing it):

```bash
RABBIT_MQ_HOST=localhost
```

The remaining defaults (`root:root` for MySQL, `guest:guest` for RabbitMQ) are fine for local use.

---

## Step 3 — Start infrastructure (MySQL + RabbitMQ)

```bash
docker compose up -d mysql rabbitmq
```

Give them ~15 seconds to pass their health checks before continuing.

- RabbitMQ management UI: http://localhost:15672 (login `guest` / `guest`)

---

## Step 4 — Backend

New terminal, venv active:

```bash
cd backend
PYTHONUTF8=1 python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Use **port 8000** (matches the frontend's API base, see Step 6). `--host 0.0.0.0` is required for
anyone other than you to reach it — uvicorn defaults to `127.0.0.1` (loopback-only), which refuses
every connection that isn't from the same machine, no matter what firewall/router rules you add.
Tables auto-create on first startup.

- Backend API: http://localhost:8000 (or `http://<your LAN/public IP>:8000` from elsewhere)

---

## Step 5 — Generator

New terminal, venv active. Feeds live telemetry into MySQL so there's data to display and train on:

```bash
cd rabbitmq/producer/publisher
python publisher.py
```

Leave it running.

---

## Step 6 — Frontend

New terminal (needs Node):

```bash
cd frontend
npm install
cp .env.example .env   # then set VITE_API_URL — see below
npm run dev
```

- Dashboard: http://localhost:3000 (port set in `vite.config.ts`)

`vite.config.ts` has `server.host: true`, so the dev server listens on all network interfaces —
required for anyone but you to reach it, same reasoning as the backend's `--host 0.0.0.0`.

**`VITE_API_URL` in `frontend/.env`** — the dashboard's JS calls this URL from the *viewer's*
browser, so it must be an address **they** can resolve, not "localhost" (which always means the
viewer's own machine, never your server):

| Who's viewing | Set `VITE_API_URL` to |
|---|---|
| You, same machine | `http://localhost:8000` (default, no `.env` needed) |
| Another device on your LAN | `http://<your LAN IP>:8000`, e.g. `http://192.168.18.3:8000` |
| Another network / the internet | `http://<your public IP or domain>:8000` |

Restart `npm run dev` after changing `.env` (Vite only reads it at startup).

At this point the dashboard is fully functional. The ML step below is only needed for the
prediction / maintenance features.

---

## Step 7 — ML model

New terminal, venv active, from repo root. Let the generator run for a while first so there's
data to learn from, then:

```bash
python -m ml.train                  # train the XGBoost model
python -m ml.registry --bootstrap   # register it as v1 Production
python -m ml.schedule               # optional: background retrain / drift / feedback worker
```

---

## Startup order (quick reference)

1. Infra: MySQL + RabbitMQ (Docker)
2. Backend (terminal 1, venv) — **port 8000**
3. Generator (terminal 2, venv)
4. Frontend (terminal 3)
5. ML — once data exists (terminal 4, venv)

Every Python service (backend, generator, ML) needs the venv activated in its own terminal.
The `.env` is auto-loaded by each service, so you don't need to `export` anything manually.

---

## Common issues

| Symptom | Fix |
|---|---|
| Dashboard loads but all data is empty | Backend must be on port **8000**, not 8077. |
| Publisher can't connect to broker | Add `RABBIT_MQ_HOST=localhost` to `.env`. |
| Backend can't connect to MySQL | Wait for the MySQL container's health check; confirm `DATABASE_URL` uses `@localhost`. |
| ML training has nothing to learn from | Let the generator run longer before `python -m ml.train`. |
| Port forwarded, but "unable to connect" from another network | Almost always one of: (1) uvicorn/Vite still bound to loopback only — see below; (2) no Windows Firewall inbound rule for the port; (3) `VITE_API_URL` unset or set to `localhost`, so the *viewer's* browser tries to reach itself instead of your server. |

---

## Remote / cross-network access

Reaching the dashboard from another device — especially another network — needs all three of
these, not just router port-forwarding:

1. **Services bound to `0.0.0.0`, not loopback.** By default both uvicorn and Vite listen only on
   `127.0.0.1`/`::1`, which rejects every connection that isn't from the same machine — no
   firewall or router setting can override this, since the OS never even hands the connection to
   the process. Already set for you: backend uses `--host 0.0.0.0` (Step 4), frontend has
   `server.host: true` in `vite.config.ts`.
2. **Windows Firewall inbound rules** for each port you're exposing (3000 for the frontend, 8000
   for the backend if it's reached directly). Create them (run PowerShell as Administrator):
   ```powershell
   New-NetFirewallRule -DisplayName "Dashboard Frontend 3000" -Direction Inbound -Protocol TCP -LocalPort 3000 -Action Allow
   New-NetFirewallRule -DisplayName "Dashboard Backend 8000"  -Direction Inbound -Protocol TCP -LocalPort 8000  -Action Allow
   ```
3. **`VITE_API_URL` pointing at an address the viewer can resolve** (Step 6) — the dashboard's API
   calls happen in the *viewer's* browser, so `localhost` in that URL means the viewer's own
   machine, not yours. Set it to your LAN IP for same-network access, or your public IP/domain for
   cross-network access (with port 8000 forwarded on your router too, same as 3000).

Verify each layer independently when debugging: `netstat -an | findstr :3000` should show
`0.0.0.0:3000` (not `127.0.0.1` or `[::1]`) once the service is bound correctly; then confirm the
firewall rule exists; then confirm the port is actually forwarded on your router; then confirm
`VITE_API_URL` is correct.
