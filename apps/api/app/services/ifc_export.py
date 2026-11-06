"""IFC export (M34). Element identity and properties, no geometry.

Writes a valid IFC4 file containing:
  - Project -> Site -> Building -> BuildingStorey spatial hierarchy
  - One element per BimElement row, in the storey matching its level
  - One property set per prefix in the element's properties
  - A `BIMGuard.SourceClass` property when the source class is not a valid
    IFC product class (fallback to IfcBuildingElementProxy)

What this does NOT write:
  - Geometry: no IfcProductDefinitionShape, no IfcExtrudedAreaSolid,
    no representations at all. Elements appear in the IFC tree but are
    invisible in viewers that render geometry (they will still appear in
    the tree, in property views, and in IfcOpenShell's by_type results).
  - Materials: BimElement.material is stored as a pset property, not as
    an IfcMaterial/IfcRelAssociatesMaterial chain.
  - IfcOpeningElement, IfcSpace boundaries, quantities as formal IFC
    quantity entities. Room and material values are psets only.

Round-trip contract: the exported file, when read back through
IfcProvider, produces the same element set (by tag), class (for valid
IFC classes), name, level, room, material, and properties as the source.
Verified by tests/test_ifc_export.py.

Why geometry is not exported: writing valid IfcShapeRepresentation from
a `geometry` dict that only has a bounding box location requires a
nontrivial conversion. The exporter ships without geometry so it can be
documented honestly as "identity + psets only". See
docs/architecture/ifc-export.md.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.bim import BimElement
from app.models.document import DocumentRevision

log = logging.getLogger("bimguard.ifc_export")


@dataclass
class IfcExportResult:
    content: bytes
    element_count: int
    level_count: int
    skipped_elements: int
    warnings: list[str] = field(default_factory=list)


def _flatten_props(props: dict) -> dict[str, Any]:
    """Convert nested values to JSON strings so edit_pset accepts them."""
    out: dict[str, Any] = {}
    for k, v in (props or {}).items():
        if v is None:
            continue
        if isinstance(v, (dict, list, tuple)):
            out[k] = json.dumps(v, default=str)
        else:
            out[k] = v
    return out


def _split_by_pset(props: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Group 'Pset.Foo = x' into {'Pset': {'Foo': x}}.

    Keys without a dot go to 'BIMGuardExtracted'.
    """
    out: dict[str, dict[str, Any]] = {}
    for key, value in props.items():
        if "." in key:
            pset_name, prop_name = key.split(".", 1)
        else:
            pset_name, prop_name = "BIMGuardExtracted", key
        out.setdefault(pset_name, {})[prop_name] = value
    return out


def export_revision_to_ifc(
    db: Session, revision: DocumentRevision, *,
    project_name: str = "BIMGuard Export",
) -> IfcExportResult:
    import ifcopenshell
    import ifcopenshell.api
    # M34: submodules are lazily loaded in ifcopenshell>=0.8; explicit imports
    # are required so api.project / .root / .unit / .aggregate / .spatial /
    # .pset resolve at call time.
    import ifcopenshell.api.project  # noqa: F401
    import ifcopenshell.api.root  # noqa: F401
    import ifcopenshell.api.unit  # noqa: F401
    import ifcopenshell.api.aggregate  # noqa: F401
    import ifcopenshell.api.spatial  # noqa: F401
    import ifcopenshell.api.pset  # noqa: F401

    elements = list(db.scalars(
        select(BimElement).where(BimElement.revision_id == revision.id)
    ))

    f = ifcopenshell.api.project.create_file(version="IFC4")
    project = ifcopenshell.api.root.create_entity(f, ifc_class="IfcProject")
    project.Name = project_name
    ifcopenshell.api.unit.assign_unit(f)
    site = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSite")
    site.Name = "Site"
    building = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuilding")
    building.Name = "Building"
    ifcopenshell.api.aggregate.assign_object(f, relating_object=project, products=[site])
    ifcopenshell.api.aggregate.assign_object(f, relating_object=site, products=[building])

    levels: dict[str, list[BimElement]] = {}
    for e in elements:
        levels.setdefault(e.level or "(no level)", []).append(e)

    storeys: dict[str, Any] = {}
    for level_name in sorted(levels):
        storey = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuildingStorey")
        storey.Name = level_name
        ifcopenshell.api.aggregate.assign_object(f, relating_object=building, products=[storey])
        storeys[level_name] = storey

    warnings: list[str] = []
    skipped = 0

    for level_name in sorted(levels):
        storey = storeys[level_name]
        for elem in levels[level_name]:
            props = _flatten_props(dict(elem.properties or {}))
            # M34: persist room and material as psets so the reader
            # (IfcProvider) can recover them after round-trip.
            if elem.room:
                props["BIMGuardElement.Room"] = elem.room
            if elem.material:
                props["BIMGuardElement.Material"] = elem.material
            source_class = elem.ifc_class or ""

            entity = None
            try:
                cand = ifcopenshell.api.root.create_entity(f, ifc_class=source_class)
                if cand.is_a("IfcProduct"):
                    entity = cand
                else:
                    f.remove(cand)
            except (TypeError, RuntimeError, KeyError, Exception) as exc:  # noqa: BLE001
                log.debug("class %r not usable (%s); falling back", source_class, exc)

            if entity is None:
                try:
                    entity = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuildingElementProxy")
                    props["BIMGuard.SourceClass"] = source_class or "(unknown)"
                    warnings.append(f"{elem.tag or elem.guid}: exported as IfcBuildingElementProxy")
                except Exception as exc:  # noqa: BLE001
                    skipped += 1
                    warnings.append(f"{elem.tag or elem.guid}: could not create any entity ({exc})")
                    continue

            if elem.name:
                entity.Name = elem.name
            if elem.tag and hasattr(entity, "Tag"):
                try:
                    entity.Tag = elem.tag
                except Exception:
                    pass

            try:
                ifcopenshell.api.spatial.assign_container(f, relating_structure=storey, products=[entity])
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"{elem.tag or elem.guid}: could not assign to storey ({exc})")

            for pset_name, pset_props in _split_by_pset(props).items():
                try:
                    pset = ifcopenshell.api.pset.add_pset(f, product=entity, name=pset_name)
                    ifcopenshell.api.pset.edit_pset(f, pset=pset, properties=pset_props)
                except Exception as exc:  # noqa: BLE001
                    warnings.append(
                        f"{elem.tag or elem.guid}: pset {pset_name} dropped ({exc})"
                    )

    content = f.to_string().encode("utf-8")
    log.info(
        "IFC export: revision=%s elements=%d levels=%d bytes=%d",
        revision.id, len(elements), len(levels), len(content),
    )
    return IfcExportResult(
        content=content,
        element_count=len(elements),
        level_count=len(levels),
        skipped_elements=skipped,
        warnings=warnings,
    )