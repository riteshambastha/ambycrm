# AmbyChat — AI-Powered Enterprise Hub

A multi-tenant SaaS platform that unifies CRMs, email, documents, and meetings into a single AI-powered chat interface.

## Architecture

```
ambycrm/
├── frontend/          # Next.js 16 (App Router) + Tailwind + Shadcn UI
├── backend/           # Python FastAPI + SQLAlchemy 2 + PostgreSQL
├── docker-compose.yml # Local dev: postgres + redis + backend + frontend
└── .env.example       # All required environment variables
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16 (App Router), Tailwind CSS, Shadcn UI |
| Auth | Clerk (Magic Links, OAuth, Multi-tenancy) |
| Backend | FastAPI, SQLAlchemy 2 async, Alembic |
| Database | PostgreSQL 16 |
| Cache/Queue | Redis + Celery |
| AI/LLM | LiteLLM (OpenAI GPT-4o, Anthropic Claude) |
| Encryption | Cryptography Fernet (OAuth token encryption at rest) |

## Quick Start (Local Dev)

### Prerequisites
- Node.js 20+, Python 3.12+, Docker

### 1. Clone and configure
```bash
cp .env.example .env
# Fill in: CLERK_SECRET_KEY, CLERK_PUBLISHABLE_KEY, OPENAI_API_KEY
```

### 2. Start infrastructure
```bash
docker compose up postgres redis -d
```

### 3. Run backend
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

### 4. Run frontend
```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

### Full stack (Docker)
```bash
docker compose up --build
```

## Implemented Connectors

| Connector | Category | Auth |
|-----------|----------|------|
| Salesforce | CRM | OAuth2 |
| HubSpot | CRM | OAuth2 |
| Microsoft Dynamics 365 | CRM | OAuth2 |
| SugarCRM | CRM | Password Grant |
| Google Workspace (Gmail + Drive) | Workspace | OAuth2 |
| Microsoft 365 (Outlook + OneDrive) | Workspace | OAuth2 |
| Microsoft Teams | Meetings | OAuth2 |
| Fireflies.ai | Meetings | API Key |
| Otter.ai | Meetings | API Key |
| Recall.ai | Meetings | API Key |

## Adding a New Connector

1. Create `backend/app/connectors/<category>/<name>/connector.py`
2. Implement `BaseConnector` (see `base.py` for the interface)
3. Restart the backend — it auto-discovers and registers the connector

## Database Schema Overview

- `organizations` — Tenants
- `users` — Shadow users synced from Clerk
- `organization_members` — RBAC membership (org_admin | user)
- `invitations` — Email invite tokens
- `connectors` — Static connector catalogue (seeded at startup)
- `integrations` — Per-org/user OAuth connections
- `integration_credentials` — Fernet-encrypted access/refresh tokens
- `sync_jobs` — Background sync audit log
- `conversations` — Chat threads
- `messages` — Individual messages with source citations

## Roles

| Role | Description |
|------|-------------|
| `super_admin` | Platform-level access (DB flag only) |
| `org_admin` | Manage members, integrations, org settings |
| `user` | Use chat and view connections |
