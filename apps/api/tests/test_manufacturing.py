import pytest

from app.engines.graph import Edge, RelationshipType as R
from app.engines.validation import (
    BY_ID, DocumentState, RevisionState, RuleConfig, Snapshot,
    default_configs, run_rules, validate_configuration,
)
from app.models.dependency import Dependency
from app.models.project import Project, ProjectDomain
from app.services import validation as v


def doc(id_, number, discipline="general", revision=1, status="approved"):
    revs = tuple(RevisionState(n, status if n == revision else "superseded", f"c-{id_}-{n}") for n in range(1, revision + 1))
    return DocumentState(id_, number, f"{number} doc", discipline, status, "Demo", "BIMGuard upload", revision, revs)


def edge(id_, source, target, kind=R.DEPENDS_ON, validated=1):
    return Edge(id=id_, source=source, target=target, relationship_type=kind,
                confidence=1.0, reason="test", validated_against_revision=validated)


def _make_bim_project(client, auth):
    r = client.post("/projects", json={"name": "BIM Project", "client": "C"}, headers=auth("bim_coordinator"))
    assert r.status_code == 201, r.text
    return r.json()


def _make_mfg_project(client, auth, session_factory):
    r = client.post("/projects", json={"name": "Mfg Project", "client": "C"}, headers=auth("bim_coordinator"))
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    with session_factory() as db:
        project = db.get(Project, pid)
        project.domain = ProjectDomain.MANUFACTURING
        db.commit()
    return r.json()


def test_manufacturing_relationship_types_are_registered():
    assert R.PART_OF.value == "part_of"
    assert R.SPECIFICATION_FOR.value == "specification_for"
    assert R.TEST_FOR.value == "test_for"
    assert R.WORK_INSTRUCTION_FOR.value == "work_instruction_for"


def test_manufacturing_relationship_directions():
    part = edge("e1", "part-doc", "assembly-doc", R.PART_OF)
    spec = edge("e2", "spec-doc", "part-doc", R.SPECIFICATION_FOR)
    test = edge("e3", "test-doc", "part-doc", R.TEST_FOR)
    instr = edge("e4", "instr-doc", "part-doc", R.WORK_INSTRUCTION_FOR)

    assert part.provider == "assembly-doc" and part.consumer == "part-doc"
    assert spec.provider == "part-doc" and spec.consumer == "spec-doc"
    assert test.provider == "part-doc" and test.consumer == "test-doc"
    assert instr.provider == "part-doc" and instr.consumer == "instr-doc"


def test_bim_project_excludes_part_coverage(client, auth, session_factory):
    p = _make_bim_project(client, auth)
    with session_factory() as db:
        configs = v.rule_configs(db, p["id"])
    assert "PART_COVERAGE" not in configs
    assert "MISSING_DEPENDENCY" in configs


def test_mfg_project_excludes_bim_only_rules(client, auth, session_factory):
    p = _make_mfg_project(client, auth, session_factory)
    with session_factory() as db:
        configs = v.rule_configs(db, p["id"])
    assert "PART_COVERAGE" in configs
    assert configs["PART_COVERAGE"].enabled is False
    assert "MISSING_DEPENDENCY" not in configs
    assert "SPATIAL_CONFLICT" not in configs


def test_domain_agnostic_rules_present_in_both(client, auth, session_factory):
    p_bim = _make_bim_project(client, auth)
    p_mfg = _make_mfg_project(client, auth, session_factory)
    for rid in ("MISSING_REVISION", "STALE_DEPENDENCY", "APPROVAL_REQUIRED", "READINESS_POLICY"):
        with session_factory() as db:
            assert rid in v.rule_configs(db, p_bim["id"])
            assert rid in v.rule_configs(db, p_mfg["id"])


def test_rule_configs_without_project_returns_everything(client, auth, session_factory):
    with session_factory() as db:
        configs = v.rule_configs(db)
    for rid in ("MISSING_REVISION", "MISSING_DEPENDENCY", "PART_COVERAGE", "SPATIAL_CONFLICT"):
        assert rid in configs


def test_part_coverage_validator():
    definition = BY_ID["PART_COVERAGE"]
    validate_configuration("PART_COVERAGE", definition.default_severity, definition.default_params)


def test_part_coverage_validator_rejects_empty_list():
    with pytest.raises(ValueError):
        validate_configuration("PART_COVERAGE", "MEDIUM", {"required": []})


def _run_part_coverage(snapshot, **params):
    configs = default_configs()
    configs["PART_COVERAGE"] = RuleConfig(
        "PART_COVERAGE", True, "MEDIUM",
        params if params else {"required": ["specification_for", "test_for", "work_instruction_for"]},
    )
    return [f for f in run_rules(snapshot, configs) if f.rule_id == "PART_COVERAGE"]


def test_part_coverage_fires_when_part_has_no_support():
    docs = (doc("asm", "ASM-1"), doc("part", "PART-1"))
    edges = (edge("e1", "part", "asm", R.PART_OF),)
    snap = Snapshot(documents=docs, edges=edges)
    findings = _run_part_coverage(snap)
    assert len(findings) == 1
    assert findings[0].document_number == "PART-1"
    assert findings[0].severity == "MEDIUM"


def test_part_coverage_quiet_when_spec_exists():
    docs = (doc("asm", "ASM-1"), doc("part", "PART-1"), doc("spec", "SPEC-1"))
    edges = (
        edge("e1", "part", "asm", R.PART_OF),
        edge("e2", "spec", "part", R.SPECIFICATION_FOR),
    )
    snap = Snapshot(documents=docs, edges=edges)
    assert _run_part_coverage(snap) == []


def test_part_coverage_quiet_when_test_exists():
    docs = (doc("asm", "ASM-1"), doc("part", "PART-1"), doc("test", "TEST-1"))
    edges = (
        edge("e1", "part", "asm", R.PART_OF),
        edge("e2", "test", "part", R.TEST_FOR),
    )
    snap = Snapshot(documents=docs, edges=edges)
    assert _run_part_coverage(snap) == []


def test_part_coverage_quiet_when_no_parts():
    docs = (doc("asm", "ASM-1"),)
    snap = Snapshot(documents=docs, edges=())
    assert _run_part_coverage(snap) == []


def test_part_coverage_respects_config():
    docs = (doc("asm", "ASM-1"), doc("part", "PART-1"), doc("instr", "INSTR-1"))
    edges = (
        edge("e1", "part", "asm", R.PART_OF),
        edge("e2", "instr", "part", R.WORK_INSTRUCTION_FOR),
    )
    snap = Snapshot(documents=docs, edges=edges)
    findings = _run_part_coverage(snap, required=["specification_for"])
    assert len(findings) == 1


def test_mfg_profile_loads():
    from app.engines.profiles.registry import default_dir
    from app.engines.profiles.loader import load_from_file
    path = default_dir() / "mfg-v1.yaml"
    profile = load_from_file(path)
    assert profile.id == "mfg-v1"
    assert profile.illustrative is True
    assert "PART_COVERAGE" in profile.rules
    assert profile.rules["PART_COVERAGE"].enabled is True


def test_mfg_project_end_to_end(client, auth, session_factory):
    p = _make_mfg_project(client, auth, session_factory)
    pid = p["id"]

    asm = client.post(f"/projects/{pid}/documents", headers=auth("engineer"),
                      json={"document_number": "ASM-1", "name": "Assembly", "discipline": "general"}).json()
    part = client.post(f"/projects/{pid}/documents", headers=auth("engineer"),
                       json={"document_number": "PART-1", "name": "Part", "discipline": "general"}).json()

    with session_factory() as db:
        db.add(Dependency(
            project_id=pid, source_document_id=part["id"], target_document_id=asm["id"],
            relationship_type="part_of", confidence=1.0, reason="test",
            validated_against_revision=0,
        ))
        db.commit()

    r = client.put(f"/projects/{pid}/profile", headers=auth("bim_coordinator"),
                   json={"profile_id": "mfg-v1"})
    assert r.status_code == 200, r.text

    run = client.post(f"/projects/{pid}/validate", headers=auth("engineer"))
    assert run.status_code == 201, run.text
    body = run.json()
    assert body["summary"]["by_rule"].get("PART_COVERAGE", 0) == 1
    assert "MISSING_DEPENDENCY" not in body["summary"]["by_rule"]
    assert "SPATIAL_CONFLICT" not in body["summary"]["by_rule"]