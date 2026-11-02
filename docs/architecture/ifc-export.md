# IFC export (M34)

`GET /revisions/{revision_id}/export.ifc` returns a valid IFC4 file (`model/ifc`) for a single revision.

## What the file contains

A valid IFC4 file with:

- **Spatial hierarchy** — IfcProject → IfcSite → IfcBuilding → one IfcBuildingStorey per distinct `level` on the revision's elements
- **One element per BimElement row**, in the storey matching its level, using the same class the source had (IfcWall, IfcSlab, IfcDoor, etc.)
- **Property sets** — the element's `properties` split by pset prefix (see below)
- **`BIMGuard.SourceClass`** — only when the source class is not a valid IFC product class and the element was exported as `IfcBuildingElementProxy`

## What the file does NOT contain

- **Geometry.** No shape representations. Elements appear in the spatial tree and in property views, but are invisible in 3D. A viewer will show the tree and psets; the 3D view will be empty.
- **Materials.** `BimElement.material` is written as a pset property only, not as an `IfcMaterial` / `IfcRelAssociatesMaterial` chain.
- **Quantities as IFC entities.** Values that came from `Qto_*` psets in the source are written as property sets, not as formal `IfcElementQuantity` entities.
- **Room / space boundaries.** `BimElement.room` is a pset property. IfcRelSpaceBoundary is not written.
- **Openings.** IfcOpeningElement is never exported.
- **Full BCF or IFC2X3 compatibility.** IFC4 only.

## When this is useful

- **QA and diff review.** Reading the export back through `IfcProvider` produces the same element set, tags, classes, and psets. Useful for verifying that a revision's extracted data is complete before uploading somewhere else, or for comparing two revisions structurally without re-uploading files.
- **Property audits.** Element psets survive. A reviewer who needs to check "does W-100 have a fire rating in revision 5" can do it against the exported file.
- **Plugin and integration input.** Any tool that consumes IFC element metadata (but not geometry) can consume this file.

## When this is NOT useful

- **Anything requiring geometry.** Analysis, clash detection, rendering, quantity calculation that depends on actual volume or area.
- **Reconstruction of the original IFC.** The export is derived from BIMGuard's extracted element rows, which is a lossy subset of the source IFC. Source properties that BimGuard did not extract are not in the export.
- **Submission to a receiver.** This is not a compliant IFC submission. It is a QA artifact.

## Property-set mapping

Source `properties` keys are split by their first dot:

| Source key | Exported pset | Exported property |
| :--- | :--- | :--- |
| `Pset_WallCommon.IsExternal` | `Pset_WallCommon` | `IsExternal` |
| `Qto_WallBaseQuantities.Length` | `Qto_WallBaseQuantities` | `Length` |
| `BareProperty` (no dot) | `BIMGuardExtracted` | `BareProperty` |
| `Complex.Location` (value is dict) | `Complex` | `Location` (JSON-encoded string) |

Nested values (dicts, lists) are JSON-encoded before writing. This preserves them without inventing new IFC property types.

## Class handling

Valid IFC product classes (`IfcWall`, `IfcSlab`, `IfcBeam`, `IfcColumn`, `IfcDoor`, `IfcWindow`, `IfcSpace`, `IfcBuildingElementProxy`, etc.) are exported as-is.

Invalid classes (a custom class name from a JSON fixture, an empty string) fall back to `IfcBuildingElementProxy`, and the original class is stored in `BIMGuard.SourceClass`. The export result includes a warning naming each element that was proxied.

## Round-trip guarantee

Reading the export back through `IfcProvider` produces elements with:

- Same **tag** (element Tag attribute round-trips exactly)
- Same **class** (for valid IFC classes)
- Same **name**, **level**, **room**, **material** (stored as psets/attributes as described)
- Same **properties** (pset round-trip)

**Not the same**:

- **GUID** — ifcopenshell assigns new GUIDs on export; the source GUIDs are not preserved. The tag is the identifier that round-trips.
- **Geometry** — not exported, so not read back
- **Timestamps** — the file header uses the current time

This is documented as an intentional limit. A "preserve GUIDs" feature would require manually constructing entities with `entity.GlobalId = ...` after creation, which changes round-trip expectations for all existing tests. Deferred.

## Testing

`tests/test_ifc_export.py` covers 8 scenarios:

- Empty revision → valid IFC, 0 elements
- One IfcWall with psets → round-trips tag, class, name, level, room, properties
- Multiple levels → separate storeys, all elements present, correct per-element level
- Property without dot → goes to `BIMGuardExtracted` pset
- Nested property → JSON-encoded value round-trips
- Invalid class → `IfcBuildingElementProxy` fallback, `BIMGuard.SourceClass` present
- Deterministic structure across calls (same elements, same tags, same classes)
- All common IFC classes (IfcWall/Slab/Door/Beam/Column) round-trip

`tests/test_ifc_export_endpoint.py` covers 4 endpoint tests: auth, 404, content type, valid body.

## What this milestone does NOT provide

- **Geometry export.** Would require building IfcShapeRepresentation from `BimElement.geometry`, which is not a general solution — the geometry field is a bounding box at best.
- **GUID preservation.** Documented above.
- **Material association.** `BimElement.material` is a property, not an IfcMaterial.
- **Full IFC2X3 compatibility.** IFC4 only.
- **Re-import as a "new revision".** The exported file is not a substitute for the original; uploading it as a new revision would produce a picture of BIMGuard's extraction, not of the actual model.