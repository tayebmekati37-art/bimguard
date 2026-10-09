# BIMGuard — BIM Change Impact & Information Consistency Engine
Prototype. Version control tells you what changed. BIMGuard tells you what that change could affect.
Status: Milestone 4 (revision comparison and deterministic change detection).

## Run (PowerShell)
    Copy-Item .env.example .env
    docker compose up --build
    # API docs: http://localhost:8000/docs

## Native
    cd apps/api
    python -m venv .venv; .\.venv\Scripts\Activate.ps1
    pip install -e ".[dev]"
    python -m app.seed
    uvicorn app.main:app --reload
    pytest

Demo users (local development only): admin@example.local / admin-demo-pass,
engineer@example.local / engineer-demo-pass, reviewer@example.local / reviewer-demo-pass
