# Changelog

## 0.1.0 — unreleased

* Independent priority GPS polling, live consent enforcement and position
  freshness deadlines, with lifecycle and failure-combination regression tests.
* Cancel/drain failed concurrent polls, bound response parsing and WAN discovery,
  isolate malformed WAN devices, and prevent rejected-router flows from
  reserving another router's identity.
* Clarify HACS publication prerequisites and non-atomic vendor identity checks.

* Documentation-guided experimental product_info identity with 404-only legacy
  fallback, NCOS version, WAN connection/primary state and dynamic per-WAN
  counters, link states and reset-safe monotonic average rates.
* Default-off GPS consent options and reload; validated fresh locked coordinates,
  altitude, knots, heading, satellite count and age. No raw/location diagnostics.
* Synthetic telemetry/schema/auth/recovery/privacy tests; IBR1700-600M and NCOS
  6.x/7.x remain unverified experimental targets. Wi-Fi SSID/signal and all
  controls remain deferred rather than guessed from unspecified vendor fields.

* Initial experimental, read-only local NCOS product-name integration.
* UI setup, serial identity, reauthentication/reconfiguration, shared polling,
  unload lifecycle, and privacy-safe diagnostics.
* HAVRV-inspired async, translation, typing, documentation and testing
  standards with explicit unsupported hardware/features.
* Lint/type/test coverage gates, HACS/hassfest workflows, contributor and
  coding-agent guidance, and all 54 quality-scale rule assessments.
* No verified router model, published release, or awarded quality medallion.
