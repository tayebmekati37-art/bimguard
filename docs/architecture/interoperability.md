# Engineering software interoperability (Milestone 15)

## What this milestone ships

Three operations, all built on top of existing providers. No new
dependencies, no new tables, no schema changes.

### 1. Export extracted elements as canonical JSON

`GET /revisions/{id}/elements.json`

Returns the `BimElement` rows of that revision as a document in the
`bimguard.elements/1` format that `JsonProvider` already reads. The
response is a download, with `Content-Disposition: attachment`.

This is the same shape the sample JSON fixture uses, so a downloaded
file can be uploaded back as a new revision and re-extracted without
loss.

### 2. Round-trip verification

`POST /revisions/{id}/verify-round-trip`

Exports the revision to `bimguard.elements/1`, feeds it back through
`JsonProvider`, and diffs the parsed element set against the database
rows. Returns:

- `ok` - true if the round-trip was lossless
- `element_count`, `matches`
- `missing`, `extra` - GUIDs present on one side only
- `mismatches` - per-element field differences on `ifc_class`, `name`,
  `level`, `room`, `material`

`tag` is excluded from the comparison because `JsonProvider` falls back
to the GUID when a tag is empty, so an empty source tag would always
appear to mismatch.

This verifies the canonical format. It does not verify the original
uploaded file.

### 3. Source verification

`POST /revisions/{id}/verify-source`

Re-reads the *original uploaded file* with the appropriate provider and
compares the parsed GUID set with the stored `BimElement` rows. Returns
`ok`, `reason`, `parsed_element_count`, `stored_element_count`, and the
first 50 GUIDs present only on one side.

Skips with a clear reason when:

- Extraction status is not `ok`
- The stored file path is invalid or the file is missing on disk
- The file extension is not `.ifc` or `.json`
- IFC support is unavailable (`ifcopenshell` not installed)

This is the closest thing to real "import round-trip verification" that
this stack supports: it proves the stored extraction still agrees with
the file. It is not a re-upload, and it does not re-run the change
detection or impact analysis.

## What this milestone does NOT ship

### IFC export

Not implemented. Writing valid IFC requires the IfcOpenShell write API
(`ifcopenshell.api.project.create_file` plus per-entity construction
through the API), which is a substantial addition and cannot be
verified against a reference implementation in this repository. A
future milestone can add it if the round-trip proof against a known
IFC test file is available.

### BCF 3.0 import or export

Not implemented. BCF is a ZIP of XML files with a specific schema for
topics, comments, viewpoints, and IFC GUID references. A working BCF
reader is a project in its own right. Shipping a partial implementation
labelled "BCF" would be worse than not shipping BCF at all, because
users of downstream tools would try to open the file and fail silently
in ways that are hard to diagnose.

If BCF is on the roadmap, it belongs in a milestone with a real
conformance target: at minimum round-tripping a hand-built `.bcfzip`
through a known BCF reader, with the report verifying the topic list,
the GUID list, and the required markup fields.

### Autodesk Platform Services (APS) integration

Not implemented. The `BIMProvider` interface already leaves room for an
APS adapter (the docstring in `provider.py` names it), but building that
adapter requires an APS app registration, credentials, and a network
call to the Model Derivative service. Out of scope for a repository
that runs offline and does not ship credentials.

## Testing

- `tests/test_interop.py` exercises the export shape, the round-trip
  diff, and the source-verification skip paths.
- The round-trip test uses a temp file and never touches the storage
  directory, so it works in CI without a real uploaded file.
- The source-verification tests check the skip paths (not extracted,
  file missing, unsupported format) without needing real files on disk.

## Adding an export format

1. Add a `to_<format>(elements) -> bytes` function to
   `app/services/interop.py`.
2. Add an endpoint in `app/api/documents.py` alongside `elements.json`,
   with the correct `Content-Disposition` and media type.
3. Extend `tests/test_interop.py` to check the media type and the shape
   of the output. For binary formats (IFC, BCF), assert the magic bytes.