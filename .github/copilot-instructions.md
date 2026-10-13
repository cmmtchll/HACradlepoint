# CradlePoint coding-agent configuration

Follow `CONTRIBUTING.md`, `docs/architecture.md`, `docs/security.md`, and
`quality_scale.md`. Target Python >=3.14.2,<3.15 and HA Core 2026.10.1.
This is a read-only local NCOS integration, not a NetCloud cloud client.

## Agent roles

- **Integration developer:** confirm the vendor endpoint/schema; use injected
  sessions, bounded async requests, typed runtime data, coordinator polling,
  stable router identity, translations, and correct setup/unload lifecycle.
- **Test reviewer:** exercise real Home Assistant fixtures, HTTP/schema/auth
  failures, duplicate/wrong-router prevention, reload/unload, and recovery.
  Require 96% integration coverage and 100% config-flow coverage.
- **Quality reviewer:** check every applicable Bronze/Silver/Gold/Platinum rule,
  repository evidence and exemptions, docs, HACS, hassfest, strict typing and
  the latest commit's CI results. Audit success is not a medallion.
- **Security reviewer:** preserve verified HTTPS and no-redirect behavior;
  reject credential-bearing URLs; prevent credential, address, serial,
  modem identity, location and raw-response leaks in logs/diagnostics/fixtures.

## Workflow

Inspect related code, tests and docs before changes. Do not invent CradlePoint
fields, model compatibility, or WAN health from management-API reachability.
Use synthetic credentials and IDs. Do not add TLS bypasses, broad exception
handlers, write controls, or per-entity HTTP requests.

Run every command in `CONTRIBUTING.md`, update relevant documentation and
quality evidence, and inspect all four Validate jobs for the latest commit.
Report blocked/skipped checks as unverified; do not weaken gates.
Update Home Assistant and its pytest plugin together when upgrading pins.
