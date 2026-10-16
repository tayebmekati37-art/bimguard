import pytest

from app.engines.profiles import ProfileLoadError, load_from_dict, load_from_file
from app.engines.profiles.registry import list_profiles, load_by_id, load_with_errors


def _minimal(**overrides):
    data = {
        "schema_version": 1,
        "id": "test-profile",
        "name": "Test",
        "rules": {},
    }
    data.update(overrides)
    return data


def test_minimal_profile_loads():
    p = load_from_dict(_minimal())
    assert p.id == "test-profile"
    assert p.schema_version == 1
    assert p.illustrative is True
    assert p.rules == {}


def test_profile_with_rule_override_loads():
    p = load_from_dict(_minimal(rules={"STALE_DEPENDENCY": {"severity": "CRITICAL"}}))
    assert p.rules["STALE_DEPENDENCY"].severity == "CRITICAL"
    assert p.rules["STALE_DEPENDENCY"].enabled is None


def test_unknown_rule_id_rejected():
    with pytest.raises(ProfileLoadError, match="NOT_A_REAL_RULE"):
        load_from_dict(_minimal(rules={"NOT_A_REAL_RULE": {"severity": "HIGH"}}))


def test_bad_severity_rejected():
    with pytest.raises(ProfileLoadError):
        load_from_dict(_minimal(rules={"STALE_DEPENDENCY": {"severity": "URGENT"}}))


def test_bad_params_rejected():
    with pytest.raises(ProfileLoadError):
        load_from_dict(_minimal(rules={
            "NAMING_CONVENTION": {"params": {"pattern": "[", "check_prefix": False, "prefixes": {}}}
        }))


def test_unknown_top_level_key_rejected():
    with pytest.raises(ProfileLoadError):
        load_from_dict(_minimal(unexpected="x"))


def test_bad_id_rejected():
    with pytest.raises(ProfileLoadError):
        load_from_dict(_minimal(id="Has Spaces"))


def test_invalid_yaml_file_rejected(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("id: [unterminated", encoding="utf-8")
    with pytest.raises(ProfileLoadError):
        load_from_file(bad)


def test_missing_file_rejected(tmp_path):
    with pytest.raises(ProfileLoadError):
        load_from_file(tmp_path / "does-not-exist.yaml")


def test_bundled_sample_profile_loads():
    """The shipped sample must always be valid."""
    from app.engines.profiles.registry import default_dir
    path = default_dir() / "jp-bimcim-v1.yaml"
    profile = load_from_file(path)
    assert profile.id == "jp-bimcim-v1"
    assert profile.illustrative is True
    assert "STALE_DEPENDENCY" in profile.rules


def test_list_and_load_by_id(tmp_path):
    (tmp_path / "a.yaml").write_text(
        "schema_version: 1\nid: alpha\nname: Alpha\nrules: {}\n", encoding="utf-8"
    )
    (tmp_path / "b.yaml").write_text(
        "schema_version: 1\nid: beta\nname: Beta\nrules: {}\n", encoding="utf-8"
    )
    profiles = list_profiles(tmp_path)
    assert [p.id for p in profiles] == ["alpha", "beta"]
    assert load_by_id("beta", tmp_path).name == "Beta"
    assert load_by_id("missing", tmp_path) is None


def test_invalid_files_are_skipped_by_list(tmp_path):
    (tmp_path / "good.yaml").write_text(
        "schema_version: 1\nid: good\nname: Good\nrules: {}\n", encoding="utf-8"
    )
    (tmp_path / "bad.yaml").write_text(
        "schema_version: 1\nid: bad\nname: Bad\nrules: {NOT_REAL: {}}\n", encoding="utf-8"
    )
    profiles = list_profiles(tmp_path)
    assert [p.id for p in profiles] == ["good"]

    rows = load_with_errors(tmp_path)
    assert len(rows) == 2
    assert any(name == "bad.yaml" and err for name, _, err in rows)