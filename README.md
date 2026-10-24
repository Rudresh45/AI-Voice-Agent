# AI Voice Agent Platform — Starter Blueprint

This ZIP is a structured starter scaffold for a modular AI voice-agent platform.

## Architecture
- Frontend: Next.js + TypeScript
- Backend: FastAPI + Pydantic + SQLAlchemy + Alembic
- Agent runtime: Gemini adapter, harness, orchestration, tool registry and policy boundaries
- Voice runtime: STT/TTS/session integration boundaries for Whisper, Piper and LiveKit
- Database: PostgreSQL
- Optional cache/jobs: Redis + Celery
- Local development: Docker Compose
- CI/CD: GitHub Actions
- Operations: security, deployment, backup/restore and incident runbooks

**Important:** this is an architecture scaffold, not a finished production system. Authentication, tenant isolation, model tool-calling, live voice, migrations, backup encryption/upload and deployment hardening must be implemented and tested before real customer data is used. Free hosting does not guarantee production SLA or disaster recovery.

## Local setup
1. Copy `.env.example` to `.env`, then fill in local credentials.
2. Run `docker compose up -d postgres redis`.
3. Backend:
   ```bash
   cd backend
   python -m venv .venv
   # Windows: .venv\Scripts\activate
   # macOS/Linux: source .venv/bin/activate
   pip install -e ".[dev]"
   uvicorn app.main:app --reload
   ```
4. Frontend:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
5. Agent runtime:
   ```bash
   cd agent-runtime
   python -m venv .venv
   # activate environment
   pip install -e .
   python -m app.main
   ```

API docs: `http://localhost:8000/docs`. The agent runtime expects `GEMINI_API_KEY` and `GEMINI_MODEL`.

## Security
- Never commit `.env`, API keys, database passwords or encryption keys.
- Never expose Gemini credentials in browser code.
- Tenant IDs supplied by the client are not authorization.
- Review Gemini free-tier data-use terms before sending confidential content.
- Complete auth, tenant-scoping, tool authorization, backup restore drills and security tests before production.
