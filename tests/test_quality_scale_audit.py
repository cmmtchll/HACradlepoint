"""Test strict quality-scale validation and cumulative readiness reporting."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.quality_scale_audit import RULES, AuditError, audit, main, render

type Assessment = dict[str, dict[str, str]]


@pytest.fixture
def assessment() -> Assessment:
    """Provide a complete but deliberately unmet official rule assessment."""
    return {
        rule: {
            "status": "todo",
            "comment": "Implementation and supporting tests are not yet complete.",
        }
        for rules in RULES.values()
        for rule in rules
    }


def write_assessment(root: Path, assessment: Assessment) -> Path:
    """Write an assessment under a test repository root."""
    path = root / "quality_scale.yaml"
    path.write_text(yaml.safe_dump({"rules": assessment}), encoding="utf-8")
    return path


def test_official_catalog() -> None:
    """Keep the catalog identical to all 54 official tier assignments."""
    expected = {
        "bronze": (
            "action-setup appropriate-polling brands common-modules config-flow "
            "config-flow-test-coverage dependency-transparency docs-actions "
            "docs-conditions docs-high-level-description "
            "docs-installation-instructions docs-removal-instructions "
            "docs-triggers entity-event-setup entity-unique-id "
            "has-entity-name runtime-data test-before-configure test-before-setup "
            "unique-config-entry"
        ),
        "silver": (
            "action-exceptions config-entry-unloading docs-configuration-parameters "
            "docs-installation-parameters entity-unavailable integration-owner "
            "log-when-unavailable parallel-updates reauthentication-flow test-coverage"
        ),
        "gold": (
            "devices diagnostics discovery discovery-update-info docs-data-update "
            "docs-examples docs-known-limitations docs-supported-devices "
            "docs-supported-functions docs-troubleshooting docs-use-cases "
            "dynamic-devices entity-category entity-device-class "
            "entity-disabled-by-default entity-translations exception-translations "
            "icon-translations reconfiguration-flow repair-issues stale-devices"
        ),
        "platinum": "async-dependency inject-websession strict-typing",
    }
    assert RULES == {tier: tuple(rules.split()) for tier, rules in expected.items()}
    assert sum(map(len, RULES.values())) == 54
    assert len({rule for rules in RULES.values() for rule in rules}) == 54


def test_repository_assessment() -> None:
    """Validate real evidence without claiming unfinished external requirements."""
    root = Path(__file__).resolve().parents[1]
    result = audit(root / "custom_components/cradlepoint/quality_scale.yaml", root)
    for rule in ("brands", "discovery", "discovery-update-info", "repair-issues"):
        assert result[rule]["status"] == "todo"
    assert "**bronze: NOT READY**" in render(result)


def test_complete_todo_is_valid(tmp_path: Path, assessment: Assessment) -> None:
    """Accept a complete catalog even when no tier is achieved."""
    assert audit(write_assessment(tmp_path, assessment), tmp_path) == assessment
    output = render(assessment)
    assert output.count("| todo | NOT MET |") == 54
    for tier, count in (("bronze", 20), ("silver", 30), ("gold", 51), ("platinum", 54)):
        assert f"**{tier}: NOT READY** — cumulative not met: {count}/{count}" in output
    assert "not tier achievement" in output
    assert "no official medallion" in output


@pytest.mark.parametrize(
    "content",
    (
        "",
        "null",
        "[]",
        "rules: []",
        "rules: null",
        "rules: {}\nother: value",
        "rules: [",
        "rules:\n  action-setup: todo\n  action-setup: done",
        "rules:\n  ? [unhashable]\n  : value",
        "rules: {}\nrules: {}",
    ),
)
def test_malformed_yaml_and_top_level(tmp_path: Path, content: str) -> None:
    """Reject invalid YAML, duplicate keys, and malformed root structures."""
    path = tmp_path / "quality_scale.yaml"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(AuditError):
        audit(path, tmp_path)


def test_missing_file(tmp_path: Path) -> None:
    """Convert missing assessment files into useful audit errors."""
    with pytest.raises(AuditError, match="cannot read assessment"):
        audit(tmp_path / "missing.yaml", tmp_path)


def test_invalid_encoding(tmp_path: Path) -> None:
    """Report invalid UTF-8 as a validation failure."""
    path = tmp_path / "quality_scale.yaml"
    path.write_bytes(b"\xff")
    with pytest.raises(AuditError, match="cannot read assessment"):
        audit(path, tmp_path)


@pytest.mark.parametrize("change", ("missing", "unknown", "non-string"))
def test_catalog_errors(tmp_path: Path, assessment: Assessment, change: str) -> None:
    """Reject omitted, unsupported, and malformed catalog rule names."""
    if change == "missing":
        del assessment["brands"]
    elif change == "unknown":
        assessment["invented-rule"] = assessment["brands"]
    path = write_assessment(tmp_path, assessment)
    if change == "non-string":
        path.write_text(path.read_text() + "  123: {}\n", encoding="utf-8")
    with pytest.raises(AuditError, match="catalog mismatch"):
        audit(path, tmp_path)


@pytest.mark.parametrize(
    "entry",
    (
        "todo",
        None,
        {},
        {"status": "todo"},
        {"status": "todo", "comment": "A valid explanatory reason.", "evidence": "x"},
        {"status": "DONE", "comment": "A valid explanatory reason."},
        {"status": True, "comment": "A valid explanatory reason."},
        {"status": [], "comment": "A valid explanatory reason."},
        {"status": "unsupported", "comment": "A valid explanatory reason."},
        {"status": "todo", "comment": None},
        {"status": "todo", "comment": ["An invalid reason"]},
        {"status": "todo", "comment": ""},
        {"status": "todo", "comment": "TODO"},
        {"status": "todo", "comment": "todo todo todo"},
        {"status": "exempt", "comment": "N/A"},
        {"status": "done", "comment": "....................."},
        {"status": "todo", "comment": "12345 12345 12345"},
    ),
)
def test_malformed_rule_entries(
    tmp_path: Path, assessment: Assessment, entry: object
) -> None:
    """Require an exact status/comment mapping and a meaningful explanation."""
    document: dict[str, object] = dict(assessment)
    document["brands"] = entry
    path = tmp_path / "quality_scale.yaml"
    path.write_text(yaml.safe_dump({"rules": document}), encoding="utf-8")
    with pytest.raises(AuditError, match="brands:"):
        audit(path, tmp_path)


@pytest.mark.parametrize(
    "extension", ("py", "md", "rst", "json", "yaml", "yml", "toml", "png")
)
def test_done_evidence(tmp_path: Path, assessment: Assessment, extension: str) -> None:
    """Accept supported repository-relative evidence with Markdown and lines."""
    evidence = tmp_path / "docs" / f"evidence.{extension}"
    evidence.parent.mkdir()
    evidence.write_text("Evidence", encoding="utf-8")
    assessment["brands"] = {
        "status": "done",
        "comment": f"Verified behavior in `docs/evidence.{extension}:12`.",
    }
    assert audit(write_assessment(tmp_path, assessment), tmp_path) == assessment


def test_evidence_sentence_punctuation(tmp_path: Path, assessment: Assessment) -> None:
    """Recognize evidence references that end a prose sentence."""
    (tmp_path / "README.md").write_text("Evidence", encoding="utf-8")
    assessment["brands"] = {
        "status": "done",
        "comment": "The supported behavior is documented in README.md.",
    }
    assert audit(write_assessment(tmp_path, assessment), tmp_path) == assessment


@pytest.mark.parametrize(
    "reference",
    ("missing.py", "existing.txt", "../outside.py", "/outside.py", r"C:\outside.py"),
)
def test_invalid_done_evidence(
    tmp_path: Path, assessment: Assessment, reference: str
) -> None:
    """Reject absent, unsupported, absolute, and traversing evidence paths."""
    (tmp_path / "existing.txt").write_text("Evidence", encoding="utf-8")
    assessment["brands"] = {
        "status": "done",
        "comment": f"Verified behavior in {reference} with supporting tests.",
    }
    with pytest.raises(AuditError, match="brands:.*evidence"):
        audit(write_assessment(tmp_path, assessment), tmp_path)


def test_symlink_escape(tmp_path: Path, assessment: Assessment) -> None:
    """Reject existing evidence reached through an escaping symbolic link."""
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("Evidence", encoding="utf-8")
    (root / "evidence.py").symlink_to(outside)
    assessment["brands"] = {
        "status": "done",
        "comment": "Verified behavior in evidence.py with supporting tests.",
    }
    with pytest.raises(AuditError, match="escapes repository"):
        audit(write_assessment(root, assessment), root)


def test_every_reference_must_exist(tmp_path: Path, assessment: Assessment) -> None:
    """Do not let one valid reference conceal missing supporting evidence."""
    (tmp_path / "README.md").write_text("Evidence", encoding="utf-8")
    assessment["brands"] = {
        "status": "done",
        "comment": "Verified in README.md and missing.py with supporting tests.",
    }
    with pytest.raises(AuditError, match="missing.py"):
        audit(write_assessment(tmp_path, assessment), tmp_path)


@pytest.mark.parametrize(
    "reference",
    (
        "//outside.py",
        "../outside.py",
        "foo//../outside.py",
        r"\\outside.py",
        "../outside.py.",
    ),
)
def test_valid_evidence_cannot_hide_escape(
    tmp_path: Path, assessment: Assessment, reference: str
) -> None:
    """Reject escaping references even alongside valid local file evidence."""
    (tmp_path / "README.md").write_text("Evidence", encoding="utf-8")
    assessment["brands"] = {
        "status": "done",
        "comment": f"Verified in README.md and {reference} with supporting tests.",
    }
    with pytest.raises(AuditError, match="escapes repository"):
        audit(write_assessment(tmp_path, assessment), tmp_path)


def test_symlink_loop(tmp_path: Path, assessment: Assessment) -> None:
    """Turn unresolvable symbolic links into actionable validation failures."""
    (tmp_path / "evidence.py").symlink_to("evidence.py")
    assessment["brands"] = {
        "status": "done",
        "comment": "Verified behavior in evidence.py with supporting tests.",
    }
    with pytest.raises(AuditError, match="evidence"):
        audit(write_assessment(tmp_path, assessment), tmp_path)


def test_cumulative_readiness(assessment: Assessment) -> None:
    """Include lower-tier TODO rules in every higher-tier readiness result."""
    for entry in assessment.values():
        entry["status"] = "exempt"
        entry["comment"] = "This requirement does not apply to the initial integration."
    assessment["brands"]["status"] = "todo"
    output = render(assessment)
    for tier, count in (("bronze", 20), ("silver", 30), ("gold", 51), ("platinum", 54)):
        assert f"**{tier}: NOT READY** — cumulative not met: 1/{count}" in output
    assessment["brands"]["status"] = "exempt"
    assessment["test-coverage"]["status"] = "todo"
    output = render(assessment)
    assert "**bronze: READY (self-assessed)**" in output
    assert "**silver: NOT READY** — cumulative not met: 1/30" in output
    assessment["test-coverage"]["status"] = "exempt"
    assert render(assessment).count("READY (self-assessed)") == 4


def test_markdown_escape(assessment: Assessment) -> None:
    """Keep multiline comments and vertical bars from corrupting the report."""
    assessment["brands"]["comment"] = "Missing assets | requires\nupstream work."
    assert r"Missing assets \| requires upstream work." in render(assessment)


def test_cli_summary(
    tmp_path: Path,
    assessment: Assessment,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Append the complete stdout report to an existing GitHub step summary."""
    path = write_assessment(tmp_path, assessment)
    summary = tmp_path / "summary.txt"
    summary.write_text("Earlier step\n", encoding="utf-8")
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert main(["--root", str(tmp_path), "--file", path.name]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert summary.read_text(encoding="utf-8") == "Earlier step\n" + captured.out
    assert "NOT MET" in captured.out


def test_cli_validation_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Return failure and explain malformed assessments in every output."""
    path = tmp_path / "broken.yaml"
    path.write_text("rules: [", encoding="utf-8")
    summary = tmp_path / "summary.txt"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert main(["--root", str(tmp_path), "--file", str(path)]) == 1
    captured = capsys.readouterr()
    assert "audit failed" in captured.out
    assert "cannot read assessment" in captured.err
    assert summary.read_text(encoding="utf-8") == captured.out


def test_cli_summary_write_error(
    tmp_path: Path,
    assessment: Assessment,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Fail explicitly when GitHub summary publication cannot be completed."""
    path = write_assessment(tmp_path, assessment)
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(tmp_path))
    assert main(["--root", str(tmp_path), "--file", str(path)]) == 1
    assert "cannot write GITHUB_STEP_SUMMARY" in capsys.readouterr().err


def test_executable_cli(
    tmp_path: Path, assessment: Assessment, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Execute the standalone CLI from a directory outside the repository."""
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    path = write_assessment(tmp_path, assessment)
    script = Path(__file__).resolve().parents[1] / "scripts/quality_scale_audit.py"
    result = subprocess.run(
        [sys.executable, str(script), "--root", str(tmp_path), "--file", str(path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stderr == ""
    assert "cumulative not met: 54/54" in result.stdout
