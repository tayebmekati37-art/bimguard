# 5-minute demo

Presenter script. Start the app, then follow the beats.

## Setup (before the audience arrives)

    cd C:\dev\bimguard
    powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
    powershell -ExecutionPolicy Bypass -File .\scripts\load-sample-project.ps1 -WithArchitectureV2

Login: admin@example.local / admin-demo-pass
Open: http://localhost:3000

## Beat 1 - The problem (30 s)

> "Version control tells you what changed. It does not tell you what that change could affect. On a real project, one moved wall can invalidate a structural design, a quantity take-off, and an MEP layout - and nobody notices until it is expensive."

Show the Dashboard. Point at the project card: documents, stale dependencies, open impacts, validation status.

## Beat 2 - What changed (45 s)

Click the project. Point at the health panel above the documents table.

> "A-101 moved from v12 to v13. The engine detected the change, and marked every document that depends on it as stale."

Open Dependencies. The graph auto-selects A-101 and animates the spread.

> "S-201, M-301 and Q-101 all depend on A-101. The spread is replayed one step at a time."

## Beat 3 - What it means (60 s)

Open Impact analysis.

> "Every impacted document gets a severity, a score, a formula, and a path. Nothing here is guessed - the score is computed from the strength of the relationship and the size of the change."

Click a row. The detail panel opens: why the score, which elements, which path.

> "The engineer sees exactly which walls in M-301 are within reach of the change in A-101, and how they got there."

## Beat 4 - Is it ready to issue? (60 s)

Open Validation. Click "Run validation".

> "Every rule runs against the current state. The verdict is one of three: READY, READY_WITH_WARNINGS, or BLOCKED. Critical issues cannot be acknowledged away."

Point at the readiness banner and the issue list. Show acknowledge on a non-critical issue.

## Beat 5 - The AI explanation (45 s)

Back on the project. Open Ask. Type: `what depends on A-101`. Press Ask.

> "The answer is built from facts the engine already produced. The AI layer, when enabled, only rewords those facts. Any identifier the model invents is discarded and the template is used instead."

Point at the "Template" or "AI" badge and, if shown, the "Grounding check failed" strip.

## Beat 6 - Reports and audit (45 s)

Open Reports. Click "Download PDF".

> "Every project can be exported as JSON, CSV, or a printable PDF. Same data, three formats, one command."

Open Audit.

> "Every change is logged: who, when, what entity, what project."

## Beat 7 - Close (15 s)

> "BIMGuard sits on top of the tools teams already use. It adds the one thing they do not have: a deterministic, explainable answer to what did this change actually affect, and are we ready to issue."

## If AI is not configured

The Ask page still works. Every answer comes from the deterministic templates. The "AI not configured" note appears next to the toggle.

## Reset for the next demo

    cd C:\dev\bimguard
    powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1
    powershell -ExecutionPolicy Bypass -File .\scripts\load-sample-project.ps1 -WithArchitectureV2