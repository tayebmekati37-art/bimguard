# The deterministic pipeline

Every result BIMGuard produces follows the same flow. Every step is pure:
no random numbers, no network calls, no AI. Optional AI runs only at the
very end and can never change a finding.

## Flow

    upload revision
        |
        v
    [1] Extraction     IFC -> ElementData, JSON -> ElementData
        |              (per-provider; see app/bim/)
        v
    [2] Diff           from_revision vs to_revision -> DetectedChange rows
        |              (app/engines/change/)
        v
    [3] Impact         for each downstream document, score severity
        |              (app/engines/impact/ + app/engines/graph/)
        v
    [4] Validation     every enabled rule runs against a Snapshot
        |              (app/engines/validation/)
        v
    [5] Readiness      aggregate findings -> READY / WARNINGS / BLOCKED
        |              (app/engines/validation/runner.py:assess)
        v
    [6] Persistence    ValidationRun + ValidationIssue rows + AuditLog row
        |              (app/services/validation.py)
        v
    [7] (optional AI)  reword existing facts; discard on any identifier
                       that is not in the facts
                       (app/ai/orchestrator.py)

## Determinism guarantees

| Step | Guarantee | Enforced by |
| :--- | :--- | :--- |
| Extraction | Same file → same `ElementData` set | `test_extraction_api.py` |
| Diff | Same (from, to) → same changes | `test_change_detection.py` |
| Impact | Same snapshot → same scores | `test_impact_engine.py`, `test_graph_engine.py` |
| Validation | Same snapshot + config → same findings, same order | `test_validation_engine.py` |
| Readiness | Same findings + policy → same status | `test_validation_engine.py` |
| AI | Same facts → same template OR AI is discarded on grounding fail | `test_ai_orchestrator.py` |

## Where the code lives

| Step | Module | Key file |
| :--- | :--- | :--- |
| Extraction | `app.bim` | `provider.py`, `ifc_provider.py`, `json_provider.py` |
| Diff | `app.engines.change` | `detect.py` |
| Graph | `app.engines.graph` | `types.py`, `graph.py` |
| Impact | `app.engines.impact` | `analyze.py` |
| Validation | `app.engines.validation` | `definitions.py`, `rules.py`, `runner.py` |
| Readiness | `app.engines.validation` | `runner.py:assess` |
| Orchestration | `app.services.validation` | `run_validation` |
| AI (optional) | `app.ai` | `orchestrator.py`, `grounding.py` |

## AI safety boundaries

Three rules hold no matter how the AI layer evolves:

1. **AI never reads the database.** It receives facts that were already
   retrieved by `app/services/validation.py` and `app/ai/retrieval.py`.
2. **AI never adds or removes a finding.** The facts already contain the
   findings. AI only rewords them.
3. **AI is discarded on any grounding violation.** If the model produces
   an identifier (document number, element tag, revision, link) that is
   not in the facts, the entire reply is thrown away and the deterministic
   template is used instead. The violations are recorded on the AIQuery
   row for review.

The grounding check is enforced by `app/ai/grounding.py:check` and tested
in `tests/test_ai_grounding.py`.

## What determinism does NOT guarantee

- **Different revisions → different results.** The pipeline is
  deterministic given the same inputs; it does not claim that all valid
  inputs produce the same output.
- **Cross-version stability.** A future engine version may compute
  different scores for the same input. Each `ValidationRun` records its
  `rules_snapshot` so historical runs keep the configuration they were
  created with.
- **AI output stability.** Even with the same facts and provider, the
  model may produce different wording. That is why the template answer
  is the source of truth and AI is optional.