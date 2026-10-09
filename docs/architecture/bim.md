# BIM layer (Milestone 3)

## Provider abstraction
`app/bim/provider.py` defines `BIMProvider`: `import_model(path)`, `list_elements()`, `get_element(guid)`,
`get_properties(guid)`, `get_geometry(guid)`. (`compare_models` is added with change detection in Milestone 4,
where it delegates to the pure comparison engine.) Implementations:

| Provider | Input | Purpose |
|---|---|---|
| `IfcProvider` | `.ifc` via IfcOpenShell | Open-format BIM, the primary demonstration format |
| `JsonProvider` | `bimguard.elements/1` JSON | Quantities, equipment schedules, other structured data |
| `MockProvider` | in memory | Tests and demos, no filesystem |

An Autodesk Platform Services adapter would implement the same interface. It is **not implemented**, and no
APS credentials are used or required.

## Neutral element model
`ElementData`: `guid`, `ifc_class`, `name`, `tag`, `level`, `room`, `material`, `properties`, `geometry`.
All lengths are millimetres. `geometry` is `{location: [x, y, z], rotation_deg, dimensions: {Length, Width, Height}}`.
`fingerprint()` is a SHA-256 of every field except the id; Milestone 4 uses it to find changed elements quickly,
then compares field by field for the detailed change records.

## What the IFC provider extracts
Products (`IfcElement` except openings, plus `IfcSpace`), attributes, property sets, quantity sets (`Qto_*`),
materials, local placement (composed through the placement chain, converted to mm with the model's unit scale),
and spatial containment: the storey (`level`) and, for elements contained in an `IfcSpace`, the room.
For rectangular extruded bodies it also stores the body's local extent (`footprint`), used by the 2D plan view and body-size change detection. It does **not** tessellate geometry. Location, rotation and quantity-based dimensions are what change detection
compares. Full IFC geometry diffing is a documented future extension.

## Extraction pipeline
Upload stores the file and creates the revision (committed), then schedules `extract_revision` as a background
task. It opens its own session, parses the model, replaces the revision's `bim_elements` rows in batches of 1000
and records `extraction_status` (`pending`, `ok`, `failed`, `unsupported`), a user-safe message and the element
count on the revision. It never raises: a failure is a visible status with a message, and "Retry extraction"
re-runs it (`POST /revisions/{id}/extract`). Extraction state is derived data, so it is deliberately outside the
immutable revision history. The background task can later move to a Redis worker without changing callers.

## Sample data
`scripts/generate_sample_data.py` writes `data/sample_ifc/*.ifc` and `data/sample_projects/factory_expansion/*.json`
(standard library only, deterministic GlobalIds). Everything is simulated. Architecture v2 differs from v1 by:
wall W-204 moved 300 mm (and door D-204A with it), door D-202A relocated from room 205 to 204, room 204
occupancy and room 203/204 areas changed, and new wall W-207. The sample structure model has a column grid at
x = 10 000 mm, which the moved wall no longer lines up with.
