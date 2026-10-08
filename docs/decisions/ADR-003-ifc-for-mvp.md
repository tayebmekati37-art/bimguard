# ADR-003: IFC as the MVP model format

**Status:** accepted

**Context.** The prototype must run locally without proprietary credentials, yet demonstrate real BIM data.

**Decision.** Use IFC (open, ISO 16739) read through IfcOpenShell as the primary format, behind a `BIMProvider`
interface. Structured JSON covers non-geometric project data. Provider-specific code never leaks past
`app/bim`; everything downstream uses `ElementData`.

**Consequences.** Anyone can reproduce the demo. Revit or APS data would need an adapter and credentials,
which are out of scope. Geometry comparison uses placement and quantities rather than meshes, which is enough to
show change propagation but is not a clash-detection engine.
