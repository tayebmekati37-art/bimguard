# End-to-end tests

Playwright runs Chromium against the BIMGuard API and an isolated SQLite database.

## First-time setup

From the repository root:

```powershell
cd apps/web
npm ci
npx playwright install chromium
cd ../..
```

The Python environment must exist at `apps/api/.venv`.

## Run on Windows

From the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\run_m11_e2e.ps1
```

The runner creates a uniquely named temporary SQLite database, applies migrations, seeds five test accounts, starts the API on port 8100, and lets Playwright start Next.js on port 3100. It then stops the API and removes its temporary database.

It does not modify `bimguard_dev.db` or `e2e.db`.

## Test accounts

All accounts use the local test password `admin-demo-pass`.

| Role | Email |
|---|---|
| Admin | admin@example.local |
| BIM coordinator | coordinator@example.local |
| Engineer | engineer@example.local |
| Reviewer | reviewer@example.local |
| Viewer | viewer@example.local |

These credentials are for local testing only.

## View the report

After a test run, from `apps/web`:

```powershell
npx playwright show-report
```

Alternatively, open `apps/web/playwright-report/index.html` from the repository root.

## Headed vs headless

Locally, the browser is visible and slowed down (150 ms per action) so you can watch. In CI, `headless: process.env.CI === "true"` hides it.

## Test inventory

- `01-auth.spec.ts` — login, wrong password, and correct login
- `02-project.spec.ts` — dashboard, projects list, project creation, and detail page
- `03-reports.spec.ts` — readiness page and JSON download
- `04-ask.spec.ts` — question submission and template answer
- `05-audit.spec.ts` — audit log and filtering
- `06-notifications.spec.ts` — notifications page and header bell
- `07-demo.spec.ts` — demo project, readiness, language switcher, and notifications

## Adding a test

Add a `.spec.ts` file under `apps/web/e2e/`. Import shared helpers from `./helpers.ts`. Keep tests independent.
