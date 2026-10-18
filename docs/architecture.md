# Architecture

## `custom_components/cradlepoint`

* **`api.py`** — Time-, response-size-, and JSON-depth-bounded asynchronous HTTP access through Home Assistant's
  injected session, origin validation, safe exception types, and normalized
  product identity, preferring documented product_info with 404-only legacy fallback.

* **`telemetry.py`** — Frozen typed snapshots and allowlisted documentation-guided
  firmware/WAN/GPS parsers, finite/range checks and reset-safe monotonic rates.
  Malformed individual WAN members are isolated from healthy devices; invalid
  top-level trees and excessive device counts reject the WAN capability.

* **`config_flow.py`** — User onboarding, duplicate prevention,
  reauthentication, reconfiguration and default-off translated GPS consent.
  All submitted connections are
  validated before persistent changes. Home Assistant flow helpers schedule one
  reload for connection changes and changed options, without an update listener.

* **`coordinator.py`** — Shared identity-first router telemetry polling plus a
  separate, default-off identity-first GPS coordinator. Enabled GPS has its own
  60-second schedule and does not wait for firmware/WAN requests. Authentication
  failures propagate to reauthentication; failed concurrent router polls cancel
  and drain unfinished siblings. GPS consent is checked before reads and
  publication, and freshness deadlines invalidate positions without waiting
  for another network request.

* **`__init__.py`** — Typed config-entry runtime data, first refresh, platform
  forwarding and unload lifecycle.

* **`sensor.py`** — Serial-based device and sensor identity, product name, and
  coordinator-backed availability, bounded dynamic WAN entity discovery, totals/rates
  and opted-in location sensors. No entity makes independent HTTP requests.

* **`diagnostics.py`** — Minimal, allowlisted diagnostic information, with no
  config-entry secrets or raw API payload export.

* **`manifest.json`, `strings.json`, `translations/en.json`, `icons.json`** —
  Integration discovery metadata, English UI messages and entity/icon
  translations. Runtime requirements are empty: HA supplies aiohttp.

* **`quality_scale.yaml`** — Complete official checklist with rationale and
  repository evidence.

* **`brand/icon.png`** — Original, brand-neutral router artwork licensed with
  this repository. HACS accepts this local icon; it is not the manufacturer's
  logo or evidence of an official Home Assistant branding/quality award.

## Repository validation

`pyproject.toml` defines development dependencies and lint/type/test gates.
`tests` contains mocked API and Home Assistant lifecycle/flow tests plus
auditor tests. `scripts/quality_scale_audit.py` publishes cumulative quality
readiness without granting awards. `.github/workflows/validate.yml` runs
independent lint/types, tests/audit, HACS, and hassfest jobs.

## Extension boundaries

Keep the API client independent of entities; normalize confirmed fields
before exposing them. Use shared coordinator snapshots and stable serial-based
IDs, with GPS entities subscribed to the independent GPS stream. Unknown readings
remain unknown, never zero or fabricated healthy states.
Adding control actions is a separate reviewed feature, not part of telemetry
parsing. Do not expand supported hardware claims based solely on fixtures.

Identity checks precede each stream's requests; the vendor endpoints do not
provide an atomic identity-and-telemetry transaction. A management address
switching between routers during a poll cannot be proven safe by a precheck
alone. LAN GPS/NMEA streaming is not implemented; adding another source requires
verified hardware support, source authentication/trust assessment, freshness
arbitration and failover tests rather than competing entity writers.
