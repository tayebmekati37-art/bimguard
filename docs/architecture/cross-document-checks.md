# Cross-document element checks (Milestone 14)

## What these rules are

Three rules compare element data between two documents that the dependency
graph says should agree:

- `CROSS_DOC_TAG_MISSING` (MEDIUM, on by default) - the provider document
  has a tag the consumer document does not.
- `CROSS_DOC_PROPERTY_DIVERGENCE` (MEDIUM, on by default) - the same tag
  exists in both, but `level`, `room` or `material` disagree.
- `CROSS_DOC_TAG_UNEXPECTED` (LOW, off by default) - the consumer has a
  tag the provider does not.

Each rule walks the dependency graph. Only edges where **both** endpoints
have extraction status `ok` and element counts under the per-document cap
are compared. If either side has no extracted element data (PDF, DWG,
RVT, failed extraction, oversized model), the pair is skipped silently.

## What these rules are not

They do **not** verify that a 2D drawing agrees with a 3D model. That would
require parsing the drawing, comparing sheet annotations against model
geometry, and reconciling coordinate systems. BIMGuard does not do any of
that. The IFC provider extracts attributes, psets, quantities and
placement; it does not tessellate, and PDF/DWG/RVT files are stored but
not parsed.

Rules in this file compare **element lists and element properties between
IFC/JSON documents that the graph links**. A passing cross-document check
means the two model files are consistent with each other, not that a
drawing matches the model.

The comparison is limited to `level`, `room` and `material` because those
are the only per-element fields that every supported extractor reliably
populates with comparable values.

## Configuration

Each rule accepts:

- `relationship_types` - which dependency relationship types to inspect.
  Default: `depends_on`, `references`, `generated_from`, `derived_from`,
  `quantity_based_on`. Two-way types (such as `spatially_related_to`) are
  not in the default set because they do not imply that one document
  provides information to the other.
- `compare` (only for `CROSS_DOC_PROPERTY_DIVERGENCE`) - which properties
  to compare. Default: `level`, `room`, `material`.

`CROSS_DOC_TAG_UNEXPECTED` is disabled by default. Some consumer documents
legitimately add elements the provider never had (a structural model might
split a wall into several pieces). Enabling it should be a deliberate
choice for a project where that is known not to happen.

## Determinism

The rules iterate the graph in the order edges appear in the snapshot (the
same order every run), then iterate tags in sorted order. Findings are
deterministic for a given project state.

Each finding's `evidence` string encodes the state that caused it:
- `CROSS_DOC_TAG_MISSING` / `CROSS_DOC_TAG_UNEXPECTED`: `"{document}:{tag}"`.
  If the tag later appears or disappears, the fingerprint changes.
- `CROSS_DOC_PROPERTY_DIVERGENCE`: `"{field}={provider_value}/{consumer_value}"`
  per differing field. If either value changes, the fingerprint changes.

Acknowledgements persist because the fingerprint is stable while the
problem remains.

## Testing

- `tests/test_cross_document.py` exercises each rule directly against a
  hand-built `Snapshot`: positive, negative, boundary, missing-field
  skip, disallowed relationship type, default-disabled behaviour.
- The end-to-end test creates two real documents, seeds `BimElement` rows,
  and calls `build_snapshot` + `run_rules` against the real database
  stack to prove the wiring in `services/validation.py` actually
  populates `elements_by_document`.