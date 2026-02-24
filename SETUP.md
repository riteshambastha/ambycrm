# AmbyChat — Local Setup Guide

## Prerequisites

- Node.js 20+
- Python 3.12+
- Docker Desktop (running)

---

## Step 1 — Configure environment variables

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

| Variable | Where to get it |
|----------|----------------|
| `CLERK_SECRET_KEY` | https://dashboard.clerk.com → API Keys |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | https://dashboard.clerk.com → API Keys |
| `OPENAI_API_KEY` | https://platform.openai.com/api-keys |
| `ENCRYPTION_KEY` | Run the command below to generate one |

**Generate an encryption key:**
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install cryptography
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```
Copy the output and paste it as `ENCRYPTION_KEY` in `.env`.

Also update `frontend/.env.local` with your Clerk publishable key:
```
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_...
```

---

## Step 2 — Start infrastructure (Postgres + Redis)

```bash
docker compose up postgres redis -d
```

Wait for both containers to be healthy (a few seconds).

---

## Step 3 — Set up and run the backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate        # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head             # Run database migrations
uvicorn app.main:app --reload    # Start API server on http://localhost:8000
```

API docs available at: http://localhost:8000/docs

---

## Step 4 — Run the frontend

Open a new terminal tab:

```bash
cd frontend
npm install
npm run dev                      # Starts on http://localhost:3000
```

Open http://localhost:3000 in your browser.

---

## Step 5 — (Optional) Start Celery workers for background token refresh

Open two more terminal tabs:

```bash
# Worker
cd backend && source .venv/bin/activate
celery -A app.tasks.sync_tasks.celery_app worker --loglevel=info

# Scheduler (beat)
cd backend && source .venv/bin/activate
celery -A app.tasks.sync_tasks.celery_app beat --loglevel=info
```

---

## Full stack via Docker (alternative)

Runs everything in containers — requires all env vars to be set in `.env` first.

```bash
docker compose up --build
```

---

## Connector OAuth app registration

For each connector you want to use, register an OAuth app and add the credentials to `.env`:

| Connector | Developer Console |
|-----------|-------------------|
| Salesforce | https://login.salesforce.com → Setup → App Manager |
| HubSpot | https://developers.hubspot.com → Apps |
| Google Workspace | https://console.cloud.google.com → APIs & Services → Credentials |
| Microsoft 365 / Teams / Dynamics | https://portal.azure.com → App registrations |
| Fireflies | https://app.fireflies.ai → Settings → API |
| Otter.ai | https://otter.ai → Account Settings → API |
| Recall.ai | https://recall.ai → Dashboard → API Keys |

**OAuth redirect URI to register in each app:**
```
http://localhost:3000/api/oauth/callback
```

---

## Adding a new connector

1. Create `backend/app/connectors/<category>/<name>/connector.py`
2. Subclass `BaseConnector` and implement all abstract methods
3. Restart the backend — the registry auto-discovers it

See `backend/app/connectors/crm/salesforce/connector.py` as a reference.
