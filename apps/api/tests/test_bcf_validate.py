"""Tests for BCF XSD validation (M29)."""
import io
import zipfile

import pytest
from lxml import etree

from app.services.bcf import _markup_xml, _version_xml, _viewpoint_xml
from app.services.bcf_validate import (
    BCFValidationError,
    _load,
    validate_bcf_zip,
    validate_markup,
    validate_version,
    validate_viewpoint,
)


# ------------------------------------------------------------------ schemas compile

def test_all_schemas_compile():
    for name in ("bcf.version.xsd", "markup.xsd", "viewpoint.xsd"):
        schema = _load(name)
        assert isinstance(schema, etree.XMLSchema)


# ------------------------------------------------------------------ valid output passes

def test_version_xml_passes_validation():
    violations = validate_version(_version_xml())
    assert violations == [], violations


def test_viewpoint_xml_passes_validation():
    violations = validate_viewpoint(_viewpoint_xml("1aB2c3D4e5F6g7H8i9J0kL"))
    assert violations == [], violations


def test_markup_xml_passes_validation(session_factory, project):
    # Use the same helpers the bcf tests use to build a valid issue + run.
    from app.models.validation import ValidationIssue, ValidationRun
    with session_factory() as db:
        run = ValidationRun(
            project_id=project["id"], status="BLOCKED", created_by_name="Admin",
            summary={}, rules_snapshot={}, duration_ms=0,
        )
        db.add(run)
        db.flush()
        issue = ValidationIssue(
            run_id=run.id, project_id=project["id"], rule_id="STALE_DEPENDENCY",
            severity="HIGH", document_id=None, document_number="S-201",
            element_tag="", title="Stale dep", message="msg",
            recommended_action="act", details={}, fingerprint="fp", status="open",
        )
        db.add(issue)
        db.commit()
        violations = validate_markup(_markup_xml(issue, run))
    assert violations == [], violations


# ------------------------------------------------------------------ bad XML is caught

def test_markup_rejects_missing_topic():
    """A Markup with no Topic violates the schema."""
    bad = b'<?xml version="1.0"?><Markup/>'
    violations = validate_markup(bad)
    assert len(violations) > 0


def test_markup_rejects_missing_guid_attribute():
    bad = b'''<?xml version="1.0"?>
<Markup>
  <Topic TopicType="Issue" TopicStatus="Open">
    <Title>x</Title>
    <CreationDate>2020-01-01T00:00:00+00:00</CreationDate>
    <CreationAuthor>a</CreationAuthor>
  </Topic>
</Markup>'''
    violations = validate_markup(bad)
    assert any("Guid" in v for v in violations), violations


def test_markup_rejects_wrong_element_order():
    """Title must come before Priority per schema."""
    bad = b'''<?xml version="1.0"?>
<Markup>
  <Topic Guid="g" TopicType="Issue" TopicStatus="Open">
    <Priority>High</Priority>
    <Title>x</Title>
    <CreationDate>2020-01-01T00:00:00+00:00</CreationDate>
    <CreationAuthor>a</CreationAuthor>
  </Topic>
</Markup>'''
    violations = validate_markup(bad)
    assert len(violations) > 0


def test_markup_rejects_bad_datetime():
    """CreationDate must be xs:dateTime."""
    bad = b'''<?xml version="1.0"?>
<Markup>
  <Topic Guid="g" TopicType="Issue" TopicStatus="Open">
    <Title>x</Title>
    <CreationDate>not-a-date</CreationDate>
    <CreationAuthor>a</CreationAuthor>
  </Topic>
</Markup>'''
    violations = validate_markup(bad)
    assert len(violations) > 0


def test_viewpoint_rejects_missing_ifcguid():
    bad = b'''<?xml version="1.0"?>
<VisualizationInfo Guid="v">
  <Components>
    <Selection>
      <Component/>
    </Selection>
  </Components>
</VisualizationInfo>'''
    violations = validate_viewpoint(bad)
    assert any("IfcGuid" in v for v in violations), violations


# ------------------------------------------------------------------ full ZIP validation

def _make_test_zip(*entries):
    """Build a minimal ZIP in memory with the given (name, bytes) tuples."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w") as zf:
        for name, content in entries:
            zf.writestr(name, content)
    return buf.getvalue()


def test_validate_bcf_zip_accepts_good_export():
    data = _make_test_zip(
        ("bcf.version", _version_xml()),
        ("topic-1/markup.bcf", b'''<?xml version="1.0"?>
<Markup>
  <Topic Guid="t1" TopicType="Issue" TopicStatus="Open">
    <Title>x</Title>
    <CreationDate>2020-01-01T00:00:00+00:00</CreationDate>
    <CreationAuthor>a</CreationAuthor>
  </Topic>
</Markup>'''),
        ("topic-1/viewpoint.bcfv", _viewpoint_xml("1aB2c3D4e5F6g7H8i9J0kL")),
    )
    violations = validate_bcf_zip(data)
    assert violations == [], violations


def test_validate_bcf_zip_catches_missing_version():
    data = _make_test_zip(
        ("topic-1/markup.bcf", _markup_minimal()),
    )
    violations = validate_bcf_zip(data)
    assert any("missing required file: bcf.version" in v for v in violations)


def test_validate_bcf_zip_catches_bad_markup():
    data = _make_test_zip(
        ("bcf.version", _version_xml()),
        ("topic-1/markup.bcf", b'<Markup/>'),
    )
    violations = validate_bcf_zip(data)
    assert len(violations) > 0


def test_validate_bcf_zip_rejects_non_zip():
    violations = validate_bcf_zip(b"not a zip")
    assert any("not a valid ZIP" in v for v in violations)


def _markup_minimal():
    return b'''<?xml version="1.0"?>
<Markup>
  <Topic Guid="t1" TopicType="Issue" TopicStatus="Open">
    <Title>x</Title>
    <CreationDate>2020-01-01T00:00:00+00:00</CreationDate>
    <CreationAuthor>a</CreationAuthor>
  </Topic>
</Markup>'''


# ------------------------------------------------------------------ build_bcf gate

def test_build_bcf_raises_on_schema_violation(monkeypatch, session_factory, project):
    """If _markup_xml produces something the schema rejects, build_bcf raises."""
    from app.services import bcf as bcf_module
    from app.models.validation import ValidationIssue, ValidationRun

    with session_factory() as db:
        run = ValidationRun(
            project_id=project["id"], status="BLOCKED", created_by_name="Admin",
            summary={}, rules_snapshot={}, duration_ms=0,
        )
        db.add(run)
        db.flush()
        db.add(ValidationIssue(
            run_id=run.id, project_id=project["id"], rule_id="STALE_DEPENDENCY",
            severity="HIGH", document_id=None, document_number="S-201",
            element_tag="", title="x", message="m", recommended_action="a",
            details={}, fingerprint="fp", status="open",
        ))
        db.commit()

        # Replace _markup_xml to return XML that violates the schema.
        monkeypatch.setattr(bcf_module, "_markup_xml", lambda issue, run: b'<Markup/>')

        with pytest.raises(BCFValidationError) as exc_info:
            bcf_module.build_bcf(db, run)
        assert len(exc_info.value.violations) > 0


def test_build_bcf_skips_validation_when_env_disabled(monkeypatch, session_factory, project):
    from app.services import bcf as bcf_module
    from app.models.validation import ValidationIssue, ValidationRun

    monkeypatch.setenv("BCF_VALIDATE", "0")

    with session_factory() as db:
        run = ValidationRun(
            project_id=project["id"], status="BLOCKED", created_by_name="Admin",
            summary={}, rules_snapshot={}, duration_ms=0,
        )
        db.add(run)
        db.flush()
        db.add(ValidationIssue(
            run_id=run.id, project_id=project["id"], rule_id="STALE_DEPENDENCY",
            severity="HIGH", document_id=None, document_number="S-201",
            element_tag="", title="x", message="m", recommended_action="a",
            details={}, fingerprint="fp", status="open",
        ))
        db.commit()

        monkeypatch.setattr(bcf_module, "_markup_xml", lambda issue, run: b'<Markup/>')
        # With validation disabled, build_bcf returns the (invalid) bytes.
        data = bcf_module.build_bcf(db, run)
    assert isinstance(data, bytes)
    assert len(data) > 0


def test_build_bcf_passes_validation_on_real_export(client, auth, project, session_factory):
    """End-to-end: a real issue exports and validates."""
    from app.models.validation import ValidationIssue, ValidationRun

    with session_factory() as db:
        run = ValidationRun(
            project_id=project["id"], status="BLOCKED", created_by_name="Admin",
            summary={}, rules_snapshot={}, duration_ms=0,
        )
        db.add(run)
        db.flush()
        db.add(ValidationIssue(
            run_id=run.id, project_id=project["id"], rule_id="STALE_DEPENDENCY",
            severity="HIGH", document_id=None, document_number="S-201",
            element_tag="", title="Stale", message="msg", recommended_action="act",
            details={}, fingerprint="fp", status="open",
        ))
        db.commit()
        run_id = run.id

    r = client.get(f"/validation-runs/{run_id}/bcf", headers=auth("engineer"))
    assert r.status_code == 200
    violations = validate_bcf_zip(r.content)
    assert violations == [], violations