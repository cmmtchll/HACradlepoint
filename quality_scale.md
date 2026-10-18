# Home Assistant integration quality scale

## Status: experimental read-only telemetry; no medallion awarded

This project follows HAVRV's evidence-based approach to the official
[Home Assistant checklist](https://developers.home-assistant.io/docs/core/integration-quality-scale/checklist/).
Bronze and Silver are the initial implementation targets; Gold and Platinum
are tracked without claiming completion.

Every one of the 54 rules is recorded in
`custom_components/cradlepoint/quality_scale.yaml` with `done`, `exempt`,
or `todo` and an explanation. A `done` rule references repository evidence.
An `exempt` rule explains why the requirement does not apply to the current
read-only implementation. Exemptions must be reassessed when adding features.

`scripts/quality_scale_audit.py` checks the complete rule catalog, statuses,
rationales, and evidence paths. Its report includes every rule and cumulative
readiness: a higher tier cannot be ready while any lower-tier item is `todo`.
The report appears in the GitHub Actions step summary. The audit succeeds when
the tracking file is valid, even with open items; it explicitly reports unmet
tiers. File existence is not proof of runtime behavior or rule satisfaction.

Independent gates enforce Ruff lint/format, strict mypy, >=96% integration
coverage, 100% config-flow coverage, HACS validation, and hassfest. Home
Assistant's Core tier validator does not award tiers to this custom repository.
Hardware verification, human review, and full applicable criteria remain
necessary even when automated checks pass.

## Implementation gates

### Bronze

Validated setup, unique identity, async lifecycle, translated UI, stable entity
naming, dependency transparency, and complete user documentation. Official
branding assessment/assets remain open.

### Silver

Authentication recovery, entry unloading, unavailable/recovery handling,
controlled update concurrency, ownership, and >95% test coverage. Real-router
outage and credential-rotation verification remain necessary.

### Gold

Devices, privacy-safe diagnostics, reconfiguration, detailed examples and
limitations. Discovery/discovery-address updates and actionable repairs remain
unimplemented or require a documented applicability assessment.

### Platinum

Async network access, injected web session, and strict typing. All lower tiers
must also be complete before representing this tier as ready.

No model is certified supported yet. Do not place achieved-medallion badges
in the README or set a manifest quality tier without a full documented review.
Keep the catalog aligned with the upstream checklist when upgrading HA.

Documentation-guided firmware/WAN and opted-in GPS now use frozen normalized
snapshots. `tests/test_optional.py` covers optional failures/authentication,
dynamic WAN entities and GPS consent/reload; `tests/test_telemetry.py` covers
finite/range checks, unknown readings, privacy allowlists and reset-safe rates.
`tests/test_gps.py` exercises the independent priority GPS stream and lifecycle;
`tests/test_input_bounds.py` exercises bounded decoding and malformed input.
GPS does not enter diagnostics or logs, but opted-in entity states/history are
privacy-sensitive. NCOS 6.x/7.x and IBR1700-600M remain experimental, not certified.
Existing open quality gaps are not promoted by synthetic fixtures or coverage.
