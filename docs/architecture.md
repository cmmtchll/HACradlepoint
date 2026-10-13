# Architecture

`custom_components/cradlepoint`
--------------------------------

`api.py`
  Bounded asynchronous HTTP access through Home Assistant's injected session,
  origin validation, safe exception types, and normalized product identity.

`config_flow.py`
  User onboarding, duplicate prevention, reauthentication, and reconfiguration.
  All submitted connections are validated before persistent changes.

`coordinator.py`
  One shared local poll per router, identity checking, availability and
  authentication-failure propagation.

`__init__.py`
  Typed config-entry runtime data, first refresh, platform forwarding, unload
  and config-change reload lifecycle.

`sensor.py`
  Serial-based device and sensor identity, product name, and coordinator-backed
  availability. No entity makes independent HTTP requests.

`diagnostics.py`
  Minimal, allowlisted diagnostic information, with no config-entry secrets
  or raw API payload export.

`manifest.json`, `strings.json`, `translations/en.json`, `icons.json`
  Integration discovery metadata, English UI messages and entity/icon
  translations. Runtime requirements are empty: HA supplies aiohttp.

`quality_scale.yaml`
  Complete official checklist with rationale and repository evidence.

`brand/icon.png`
  Original, brand-neutral router artwork licensed with this repository.
  HACS accepts this local icon; it is not the manufacturer's logo or evidence
  of an official Home Assistant branding/quality award.

## Repository validation

`pyproject.toml` defines development dependencies and lint/type/test gates.
`tests` contains mocked API and Home Assistant lifecycle/flow tests plus
auditor tests. `scripts/quality_scale_audit.py` publishes cumulative quality
readiness without granting awards. `.github/workflows/validate.yml` runs
independent lint/types, tests/audit, HACS, and hassfest jobs.

## Extension boundaries

Keep the API client independent of entities; normalize confirmed fields
before exposing them. Use one coordinator snapshot and stable serial-based
IDs. Unknown readings remain unknown, never zero or fabricated healthy states.
Adding control actions is a separate reviewed feature, not part of telemetry
parsing. Do not expand supported hardware claims based solely on fixtures.
