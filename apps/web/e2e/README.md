# End-to-end tests

Playwright drives a real Chromium browser against a running BIMGuard.

## First time

    cd apps/web
    npm install
    npx playwright install chromium

## Run

From C:\dev\bimguard:

    powershell -ExecutionPolicy Bypass -File run_m11_e2e.ps1

The script:

1. Creates a fresh apps/api/e2e.db and seeds five users.
2. Starts the backend on 127.0.0.1:8001 as a background job.
3. Lets Playwright spawn Next.js dev on 127.0.0.1:3001.
4. Runs every spec under apps/web/e2e/.
5. Stops the backend and prints the exit code.

## Headed vs headless

Locally the browser is visible and slowed down (150 ms per action) so you can watch. In CI, `headless: process.env.CI === "true"` hides it.

## View the report

    cd apps/web
    npx playwright show-report

Or open `apps/web/playwright-report/index.html`.

## Files

- 01-auth.spec.ts - login, wrong password, correct login
- 02-project.spec.ts - dashboard, projects list, project creation, detail page
- 03-reports.spec.ts - readiness page, JSON download
- 04-ask.spec.ts - ask a question, template answer rendered
- 05-audit.spec.ts - audit log page, filter narrows results
- 06-notifications.spec.ts - notifications page, bell in header

## Adding a test

Drop a new .spec.ts under apps/web/e2e/. Import helpers from ./helpers.ts. Keep tests independent.