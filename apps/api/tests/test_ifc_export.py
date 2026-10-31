"""Round-trip tests for IFC export (M34)."""
import os
import tempfile
from pathlib import Path

import pytest

from app.bim.ifc_provider import IfcProvider
from app.models.bim import BimElement
from app.models.document import Document, DocumentRevision
from app.services.ifc_export import export_revision_to_ifc


def _seed_revision(client, auth, project, session_factory, *elements):
    """elements: (guid, class, tag, name, level, room, material, properties)"""
    doc = client.post(
        f"/projects/{project['id']}/documents",
        headers=auth("engineer"),
        json={"document_number": "A-101", "name": "X", "discipline": "architecture"},
    ).json()
    with session_factory() as db:
        rev = DocumentRevision(
            document_id=doc["id"], revision_number=1,
            file_path="x", original_filename="a.ifc", file_size=1,
            checksum="c", created_by_name="t", status="approved",
            extraction_status="ok", element_count=len(elements),
        )
        db.add(rev)
        db.flush()
        for guid, cls, tag, name, level, room, material, props in elements:
            db.add(BimElement(
                revision_id=rev.id, guid=guid, ifc_class=cls, tag=tag, name=name,
                level=level, room=room, material=material,
                properties=props, fingerprint=f"fp-{guid}",
            ))
        db.get(Document, doc["id"]).current_revision_number = 1
        db.commit()
        return rev.id


def _read_back(content: bytes):
    fd, path = tempfile.mkstemp(suffix=".ifc")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(content)
        provider = IfcProvider()
        provider.import_model(Path(path))
        return list(provider.list_elements())
    finally:
        os.unlink(path)


def _get_rev(session_factory, rev_id):
    with session_factory() as db:
        return db.get(DocumentRevision, rev_id)


# ------------------------------------------------------------------ structure

def test_empty_revision_produces_valid_ifc(client, auth, project, session_factory):
    rev_id = _seed_revision(client, auth, project, session_factory)
    with session_factory() as db:
        rev = db.get(DocumentRevision, rev_id)
        result = export_revision_to_ifc(db, rev)
    assert result.element_count == 0
    assert result.level_count == 0
    assert result.content.startswith(b"ISO-10303-21")
    assert b"FILE_SCHEMA(('IFC4'))" in result.content[:500]
    assert b"END-ISO-10303-21" in result.content[-100:]
    # Read back: no elements
    elements = _read_back(result.content)
    assert elements == []


def test_one_wall_round_trips(client, auth, project, session_factory):
    rev_id = _seed_revision(
        client, auth, project, session_factory,
        ("guid-1", "IfcWall", "W-100", "Wall 100", "L1", "101", "concrete",
         {"Pset_WallCommon.IsExternal": True, "Pset_WallCommon.FireRating": "2h"}),
    )
    with session_factory() as db:
        result = export_revision_to_ifc(db, db.get(DocumentRevision, rev_id))
    assert result.element_count == 1
    assert result.skipped_elements == 0

    elements = _read_back(result.content)
    assert len(elements) == 1
    e = elements[0]
    assert e.ifc_class == "IfcWall"
    assert e.tag == "W-100"
    assert e.name == "Wall 100"
    assert e.level == "L1"
    assert e.room == "101"
    assert e.properties.get("Pset_WallCommon.IsExternal") is True
    assert e.properties.get("Pset_WallCommon.FireRating") == "2h"


def test_multiple_levels_get_separate_storeys(client, auth, project, session_factory):
    rev_id = _seed_revision(
        client, auth, project, session_factory,
        ("g1", "IfcWall", "W-100", "Wall 100", "L1", None, None, {}),
        ("g2", "IfcWall", "W-200", "Wall 200", "L2", None, None, {}),
        ("g3", "IfcSlab", "S-100", "Slab 100", "L2", None, None, {}),
    )
    with session_factory() as db:
        result = export_revision_to_ifc(db, db.get(DocumentRevision, rev_id))
    assert result.element_count == 3
    assert result.level_count == 2
    # IFC content mentions both storeys
    text = result.content.decode("utf-8", errors="replace")
    assert 'IFCBUILDINGSTOREY' in text
    assert '"L1"' in text or "'L1'" in text
    assert '"L2"' in text or "'L2'" in text

    elements = _read_back(result.content)
    assert len(elements) == 3
    by_tag = {e.tag: e for e in elements}
    assert by_tag["W-100"].level == "L1"
    assert by_tag["W-200"].level == "L2"
    assert by_tag["S-100"].ifc_class == "IfcSlab"


def test_property_without_dot_goes_to_default_pset(client, auth, project, session_factory):
    rev_id = _seed_revision(
        client, auth, project, session_factory,
        ("g1", "IfcWall", "W-100", "Wall", None, None, None,
         {"BareProperty": "hello", "NumericValue": 42}),
    )
    with session_factory() as db:
        result = export_revision_to_ifc(db, db.get(DocumentRevision, rev_id))
    elements = _read_back(result.content)
    assert len(elements) == 1
    e = elements[0]
    assert e.properties.get("BIMGuardExtracted.BareProperty") == "hello"
    assert e.properties.get("BIMGuardExtracted.NumericValue") == 42


def test_nested_property_is_json_encoded(client, auth, project, session_factory):
    rev_id = _seed_revision(
        client, auth, project, session_factory,
        ("g1", "IfcWall", "W-100", "Wall", None, None, None,
         {"Complex.Location": {"x": 1, "y": 2}}),
    )
    with session_factory() as db:
        result = export_revision_to_ifc(db, db.get(DocumentRevision, rev_id))
    elements = _read_back(result.content)
    e = elements[0]
    # Value is JSON-encoded string
    raw = e.properties.get("Complex.Location")
    assert raw is not None
    import json as _json
    parsed = _json.loads(raw) if isinstance(raw, str) else raw
    assert parsed == {"x": 1, "y": 2}


def test_invalid_class_falls_back_to_proxy(client, auth, project, session_factory):
    rev_id = _seed_revision(
        client, auth, project, session_factory,
        ("g1", "BIMGuardCustomType", "C-1", "Custom", "L1", None, None, {}),
    )
    with session_factory() as db:
        result = export_revision_to_ifc(db, db.get(DocumentRevision, rev_id))
    assert result.element_count == 1
    assert any("IfcBuildingElementProxy" in w for w in result.warnings)

    elements = _read_back(result.content)
    assert len(elements) == 1
    e = elements[0]
    assert e.ifc_class == "IfcBuildingElementProxy"
    assert e.tag == "C-1"
    assert e.properties.get("BIMGuard.SourceClass") == "BIMGuardCustomType"


def test_bytes_are_deterministic_shape_across_calls(client, auth, project, session_factory):
    """Two exports of the same revision produce files with the same element count
    and the same tags/classes. Byte-equality is not asserted because ifcopenshell
    assigns GUIDs, which may not be stable across calls, and header timestamps
    differ."""
    rev_id = _seed_revision(
        client, auth, project, session_factory,
        ("g1", "IfcWall", "W-100", "Wall", "L1", None, None, {}),
    )
    with session_factory() as db:
        r1 = export_revision_to_ifc(db, db.get(DocumentRevision, rev_id))
        r2 = export_revision_to_ifc(db, db.get(DocumentRevision, rev_id))
    e1 = _read_back(r1.content)
    e2 = _read_back(r2.content)
    assert len(e1) == len(e2) == 1
    assert e1[0].tag == e2[0].tag
    assert e1[0].ifc_class == e2[0].ifc_class


def test_all_classes_survive_round_trip(client, auth, project, session_factory):
    """The classes IfcProvider knows about survive round-trip."""
    classes = ("IfcWall", "IfcSlab", "IfcDoor", "IfcBeam", "IfcColumn")
    elems = [(f"g{i}", cls, f"T-{i}", cls, "L1", None, None, {})
             for i, cls in enumerate(classes)]
    rev_id = _seed_revision(client, auth, project, session_factory, *elems)
    with session_factory() as db:
        result = export_revision_to_ifc(db, db.get(DocumentRevision, rev_id))
    elements = _read_back(result.content)
    read_classes = {e.ifc_class for e in elements}
    for cls in classes:
        assert cls in read_classes, f"{cls} did not round-trip"