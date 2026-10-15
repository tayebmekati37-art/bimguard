# BIMGuard - BIM change impact & information consistency engine

Version control tells you what changed. BIMGuard tells you what that change could affect.

A deterministic engine for BIM projects: detects changes between revisions, follows typed dependencies, scores impact, enforces validation rules, and produces a readiness verdict. An optional AI layer rewords facts only - it never decides anything and never invents identifiers.

**Version:** 1.0.0

## What it does

- Uploads IFC or JSON model revisions per document.
- Detects changes between revisions.
- Builds a typed dependency graph between documents.
- Scores the impact of a change on every reachable document.
- Runs validation rules and returns READY / READY_WITH_WARNINGS / BLOCKED.
- Computes per-document health (Healthy, Warning, Stale, Critical) with reasons.
- Optionally rewords the deterministic answer with AI, with a grounding check.
- Exports a readiness report as JSON, CSV, or PDF.
- Notifies affected users and logs every action.

## Run it

### Docker

    Copy-Item .env.example .env
    docker compose up --build
    # API docs: http://localhost:8000/docs
    # Web:      http://localhost:3000

### Native (Windows, PowerShell)

Backend:

    cd apps\api
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -e ".[dev]"
    python -m app.seed
    uvicorn app.main:app --reload

Frontend, second terminal:

    cd apps\web
    npm install
    npm run dev

Open http://localhost:3000

### Demo users

    admin@example.local        admin-demo-pass
    coordinator@example.local  admin-demo-pass
    engineer@example.local     admin-demo-pass
    reviewer@example.local     admin-demo-pass
    viewer@example.local       admin-demo-pass

## Tests

Backend:

    cd apps\api
    .\.venv\Scripts\python.exe -m pytest -q
    # ~285 passed, 8 skipped

End-to-end:

    cd C:\dev\bimguard
    powershell -ExecutionPolicy Bypass -File .\run_m11_e2e.ps1
    # 12 passed (headed Chrome locally)

See `apps/web/e2e/README.md`.

## Try the 5-minute demo

See `docs/demo.md`.

## AI layer (optional)

Set these before starting the backend to enable reworded answers:

    $env:AI_BASE_URL = "http://localhost:11434/v1"
    $env:AI_MODEL    = "llama3.1:8b"
    $env:AI_API_KEY  = ""

The templates always work. See `docs/architecture/ai.md`.

## Docs

- `docs/architecture/ai.md` - AI explanation layer
- `docs/architecture/reports.md` - readiness reports
- `docs/demo.md` - 5-minute demo script
- `CHANGELOG.md` - version history

## Layout

    apps/api          FastAPI backend (Python 3.12)
    apps/web          Next.js 14 frontend
    docs              Architecture and demo docs
    scripts           start.ps1, load-sample-project.ps1