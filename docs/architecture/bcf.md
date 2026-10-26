# BCF export (M23)

`GET /validation-runs/{run_id}/bcf` returns a BCF 2.1 subset ZIP (`application/vnd.bcf.zip`).

## Files

    bcf.version             (VersionId=2.1)
    <topic>/markup.bcf      (one per issue)
    <topic>/viewpoint.bcfv  (only when issue.element_tag resolves to a valid IFC GUID)

Topic GUID = issue.id. Comment GUID and viewpoint GUID are deterministic from the source data.

## Topic mapping

| BCF | Source |
| :--- | :--- |
| Topic Guid | issue.id |
| TopicStatus | Open / Closed (acknowledged) |
| Title | "{severity}: {title}" |
| Priority | severity.capitalize() |
| CreationDate | run.created_at |
| CreationAuthor | run.created_by_name |
| ModifiedDate | acknowledged_at or created_at |
| Description | Document + Element + message + recommended_action |
| Labels | [rule_id, severity, document_number] |
| Comment | Only if acknowledged (author, note, date) |

## Viewpoint

`<Component IfcGuid="...">` where IfcGuid comes from:
`issue.document_id` -> `Document.current_revision_number` -> `DocumentRevision.id` -> `BimElement(guid, tag=issue.element_tag)` -> guid must match `^[0-9A-Za-z_$]{22}$`.

If any step fails, no viewpoint for that topic. Markup still exports.

## Not exported

- `project.bcfp` (project extension)
- Camera / perspective / orthogonal
- Snapshots (PNG)
- Clipping planes, markup lines, BIM snippets
- Multiple viewpoints per topic
- Related topics, attachments

## Validation approach

Unit tests verify structure, not spec conformance. No XSD validation. A downstream tool that rejects the file for a schema reason is a bug not caught here.

## Manual test

Open the downloaded `.bcfzip` in BIMcollab, Solibri, or Revit BCF plugin. Confirm topics, labels, comments, and viewpoint highlighting for resolvable elements.