# Validation engine (Milestone 7)

"Validate for issue" runs every enabled rule against a project and decides whether it can be issued. The rules are
deterministic code in `app/engines/validation`; their configuration is data in the `rules` table. No LLM is involved.

## Flow
1. `build_snapshot` loads what the rules need once: documents with their revisions, dependencies, the **open**
   impacts from Milestone 6, element references and tags, and the shared parameters named in the rule settings.
2. `run_rules` calls each enabled rule, a pure function from the snapshot to findings. Findings are ordered by severity,
   document and rule, so the output is identical for identical input.
3. `assess` turns findings and acknowledgements into a status.
4. The run, its issues and a snapshot of the rule configuration used are stored (`validation_runs`, `validation_issues`),
   so any past result can be explained.

## Rules
| Rule | Checks | Default |
|---|---|---|
| MISSING_REVISION | a document has no revision | High |
| INVALID_REVISION_SEQUENCE | revision numbers skip more than `max_gap` | Low |
| DUPLICATE_REVISION_CONTENT | two revisions with the same checksum | Low |
| STALE_DEPENDENCY | the provider is past the revision the dependent was validated against | High |
| MISSING_DEPENDENCY | a discipline must depend on another discipline that exists in the project | Medium |
| UNRESOLVED_REFERENCE | elements say they are `BasedOn` elements that do not exist in the source | Medium |
| UNREVIEWED_DOWNSTREAM | an indirectly affected document is unreviewed (takes the impact's severity) | Medium |
| SPATIAL_CONFLICT | an element is within `clearance_mm` of a changed element (one issue per document) | High |
| OUTDATED_REFERENCE | elements are based on elements that changed | Medium |
| PARAMETER_MISMATCH | configured shared values (for example a room area) differ between documents | High |
| MISSING_METADATA | required fields (author, name, source system, change summary) are empty | Medium |
| NAMING_CONVENTION | document number pattern and discipline prefix | Medium |
| APPROVAL_REQUIRED | the current revision's status is not in `required_status` | High |
| READINESS_POLICY | open issues at or above `blocking_severity` block the release | High |

Each rule can be enabled or disabled, given another severity, and tuned through its parameters, which are validated
on save with a message that says what is wrong. Only administrators change rules; changes are audit-logged and
apply to all projects from the next run. Rules are global in this prototype; per-project overrides are a roadmap item.

## Status
- **BLOCKED**: an open issue at or above the blocking severity (default High).
- **READY WITH WARNINGS**: only lower-severity issues remain open.
- **READY**: no open issues.

## Resolving issues
Issues are resolved by fixing their cause: reviewing a dependency against the new revision, uploading corrected
information, approving a revision. Reviewing a dependency also resolves the open impacts and spatial or reference
issues that came from it.

**Acknowledging** accepts a risk, with a written reason, by an administrator, BIM coordinator or reviewer. It does
not fix anything, and **Critical issues can never be acknowledged**. An acknowledgement is stored against the issue's
fingerprint (rule, document, subject and the evidence it was observed in), so it carries over to later runs only
while the evidence is unchanged: a new revision or a different measurement brings the issue back. Acknowledgements can be revoked.

## Limitations
Rules know about what is in the model data and the registered dependencies, nothing else. A project with no
documents validates as ready with a note saying nothing was checked. The validation report (PDF, JSON, CSV) arrives
in Milestone 10; this milestone shows the result in the Validation Center.
