# Getting started

This guide takes you from a fresh clone to a working demo in under ten minutes.

## Prerequisites

- Python 3.12+
- Node.js 20+
- PowerShell (Windows) or a POSIX shell (macOS/Linux)
- Docker (optional; needed only for the containerized path)

## Native setup (recommended for evaluation)

### Terminal 1 - API

    cd apps\api
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -e ".[dev]"
    python -m app.seed
    uvicorn app.main:app --reload

API is at `http://localhost:8000`. Docs at `http://localhost:8000/docs`.

### Terminal 2 - Frontend

    cd apps\web
    npm install
    npm run dev

Frontend is at `http://localhost:3000`.

### Log in

    admin@example.local / admin-demo-pass

### Load the demo project

    powershell -ExecutionPolicy Bypass -File scripts\load-sample-project.ps1 -WithArchitectureV2

This creates a project with five documents and five dependencies, then uploads A-101 v13. The project should now be in the state described in `docs/evaluation/demo-dataset.md`.

## Docker

    Copy-Item .env.example .env
    docker compose up --build

Backend on `:8000`, Postgres on `:5432`. The web app is not containerized in this milestone; run `npm run dev` in `apps/web` against the containerized API.

## Verify the demo works

    powershell -ExecutionPolicy Bypass -File scripts\verify-demo.ps1

This loads a fresh copy of the demo, uploads A-101 v13, and asserts the specific health states, dependency staleness, and validation results the demo doc promises. Any mismatch exits non-zero.

## Run the test suite

    cd apps\api
    .\.venv\Scripts\python.exe -m pytest -q

Expected: ~353 passed, 8 skipped.

End-to-end:

    powershell -ExecutionPolicy Bypass -File .\run_m11_e2e.ps1

Expected: 12 tests pass in a visible Chrome window.

## Measure performance

    powershell -ExecutionPolicy Bypass -File scripts\benchmark.ps1

Runs validation 5 times, reports p50/p95/min/max, and confirms all runs produce identical findings. Reports observed numbers; does not claim industry benchmarks.

## Next steps

- `docs/evaluation/demo-dataset.md` - what the demo should produce
- `docs/evaluation/metrics.md` - methodology and measured results
- `docs/architecture/` - design notes for each subsystem