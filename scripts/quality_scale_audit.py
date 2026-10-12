"""Validate the official quality-scale assessment, not an awarded medallion."""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import yaml
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode

RULES: dict[str, tuple[str, ...]] = {
    "bronze": (
        "action-setup",
        "appropriate-polling",
        "brands",
        "common-modules",
        "config-flow",
        "config-flow-test-coverage",
        "dependency-transparency",
        "docs-actions",
        "docs-conditions",
        "docs-high-level-description",
        "docs-installation-instructions",
        "docs-removal-instructions",
        "docs-triggers",
        "entity-event-setup",
        "entity-unique-id",
        "has-entity-name",
        "runtime-data",
        "test-before-configure",
        "test-before-setup",
        "unique-config-entry",
    ),
    "silver": (
        "action-exceptions",
        "config-entry-unloading",
        "docs-configuration-parameters",
        "docs-installation-parameters",
        "entity-unavailable",
        "integration-owner",
        "log-when-unavailable",
        "parallel-updates",
        "reauthentication-flow",
        "test-coverage",
    ),
    "gold": (
        "devices",
        "diagnostics",
        "discovery",
        "discovery-update-info",
        "docs-data-update",
        "docs-examples",
        "docs-known-limitations",
        "docs-supported-devices",
        "docs-supported-functions",
        "docs-troubleshooting",
        "docs-use-cases",
        "dynamic-devices",
        "entity-category",
        "entity-device-class",
        "entity-disabled-by-default",
        "entity-translations",
        "exception-translations",
        "icon-translations",
        "reconfiguration-flow",
        "repair-issues",
        "stale-devices",
    ),
    "platinum": ("async-dependency", "inject-websession", "strict-typing"),
}
STATUSES = frozenset({"done", "todo", "exempt"})
_EVIDENCE = re.compile(
    r"(?<![\w.-])(?:[A-Za-z]:[/\\]+|[/\\]+)?"
    r"(?:[\w.-]+[/\\]+)*[\w.-]+\.(?:py|md|rst|json|yaml|yml|toml|png)"
    r"(?![\w.-])"
)
_PLACEHOLDERS = frozenset(
    {"todo", "tbd", "n/a", "na", "none", "unknown", "pending", "done", "exempt"}
)


class AuditError(ValueError):
    """Indicate a malformed or unsupported quality-scale assessment."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate mapping keys rather than silently replacing rules."""

    def construct_mapping(
        self, node: MappingNode, deep: bool = False
    ) -> dict[Any, Any]:
        """Construct a mapping with unique, hashable keys."""
        seen: set[object] = set()
        construct_object = cast(Callable[..., object], self.construct_object)
        for key_node, _ in node.value:
            key = construct_object(key_node, deep=deep)
            try:
                if key in seen:
                    raise ConstructorError(
                        None, None, f"duplicate key: {key}", key_node.start_mark
                    )
                seen.add(key)
            except TypeError as err:
                raise ConstructorError(
                    None, None, "unhashable mapping key", key_node.start_mark
                ) from err
        return super().construct_mapping(node, deep=deep)


def _reason_is_meaningful(comment: str) -> bool:
    """Reject empty, placeholder-only, and non-explanatory comments."""
    words = re.findall(r"[A-Za-z][A-Za-z0-9]*", comment)
    return (
        len(comment.strip()) >= 12
        and len(words) >= 3
        and comment.strip().lower().rstrip(".!") not in _PLACEHOLDERS
        and any(word.lower() not in _PLACEHOLDERS for word in words)
    )


def _validate_evidence(rule: str, comment: str, root: Path) -> None:
    """Require existing local file evidence and reject escaping references."""
    references = _EVIDENCE.findall(comment)
    if not references:
        raise AuditError(f"{rule}: done requires repository-relative file evidence")
    root = root.resolve()
    for reference in references:
        path = Path(reference)
        if "\\" in reference or path.is_absolute() or ".." in path.parts:
            raise AuditError(f"{rule}: evidence path escapes repository: {reference}")
        try:
            resolved = (root / path).resolve()
        except (OSError, RuntimeError) as err:
            raise AuditError(f"{rule}: cannot resolve evidence: {reference}") from err
        if not resolved.is_relative_to(root):
            raise AuditError(f"{rule}: evidence path escapes repository: {reference}")
        if not resolved.is_file():
            raise AuditError(f"{rule}: evidence file does not exist: {reference}")


def audit(path: Path, root: Path) -> dict[str, dict[str, str]]:
    """Load and validate every official rule's status and explanation."""
    try:
        data: object = yaml.load(
            path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader
        )
    except (OSError, UnicodeError, yaml.YAMLError, RecursionError) as err:
        raise AuditError(f"cannot read assessment {path}: {err}") from err
    if not isinstance(data, Mapping) or set(data) != {"rules"}:
        raise AuditError("top level must contain exactly a rules mapping")
    rules = data["rules"]
    if not isinstance(rules, Mapping):
        raise AuditError("rules must be a mapping")
    expected = {rule for tier in RULES.values() for rule in tier}
    actual = set(rules)
    missing = expected - actual
    unknown = actual - expected
    if missing or unknown:
        raise AuditError(
            f"catalog mismatch; missing: {', '.join(sorted(missing)) or 'none'}; "
            f"unknown: {', '.join(sorted(map(str, unknown))) or 'none'}"
        )
    result: dict[str, dict[str, str]] = {}
    for rule in (rule for tier in RULES.values() for rule in tier):
        assessment = rules[rule]
        if not isinstance(assessment, Mapping) or set(assessment) != {
            "status",
            "comment",
        }:
            raise AuditError(f"{rule}: requires exactly status and comment")
        status = assessment["status"]
        comment = assessment["comment"]
        if not isinstance(status, str) or status not in STATUSES:
            raise AuditError(f"{rule}: status must be done, todo, or exempt")
        if not isinstance(comment, str) or not _reason_is_meaningful(comment):
            raise AuditError(f"{rule}: comment must give a meaningful reason")
        if status == "done":
            _validate_evidence(rule, comment, root)
        result[rule] = {"status": status, "comment": comment.strip()}
    return result


def _cell(value: str) -> str:
    """Keep assessment text inside a single Markdown table cell."""
    return value.replace("|", r"\|").replace("\r", " ").replace("\n", " ")


def render(assessment: Mapping[str, Mapping[str, str]]) -> str:
    """Render per-rule results and cumulative tier readiness without awards."""
    lines = [
        "# Home Assistant quality-scale self-assessment",
        "",
        "Validation success means catalog completeness, not tier achievement.",
        "Readiness is self-assessed; no official medallion is claimed.",
        "",
        "| Tier | Rule | Status | Assessment | Evidence / reason |",
        "| --- | --- | --- | --- | --- |",
    ]
    outstanding: list[str] = []
    summaries: list[str] = []
    total = 0
    for tier, rules in RULES.items():
        total += len(rules)
        for rule in rules:
            entry = assessment[rule]
            status = entry["status"]
            label = {"done": "met", "todo": "NOT MET", "exempt": "exempt"}[status]
            lines.append(
                f"| {tier} | {rule} | {status} | {label} | "
                f"{_cell(entry['comment'])} |"
            )
            if status == "todo":
                outstanding.append(rule)
        readiness = "NOT READY" if outstanding else "READY (self-assessed)"
        summaries.append(
            f"- **{tier}: {readiness}** — cumulative not met: "
            f"{len(outstanding)}/{total}; "
            f"outstanding: {', '.join(outstanding) or 'none'}"
        )
    lines.extend(["", "## Cumulative tier readiness", "", *summaries, ""])
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Validate the assessment and publish stdout and GitHub step summaries."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=Path("custom_components/cradlepoint/quality_scale.yaml"),
    )
    args = parser.parse_args(argv)
    path = args.file if args.file.is_absolute() else args.root / args.file
    try:
        output = render(audit(path, args.root))
        result = 0
    except AuditError as err:
        output = f"# Quality-scale audit failed\n\n{err}\n"
        result = 1
    print(output)
    if result:
        print(output, file=sys.stderr)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        try:
            with Path(summary).open("a", encoding="utf-8") as handle:
                handle.write(output + "\n")
        except OSError as err:
            print(f"cannot write GITHUB_STEP_SUMMARY: {err}", file=sys.stderr)
            return 1
    return result


if __name__ == "__main__":
    raise SystemExit(main())
