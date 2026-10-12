---
applyTo: "tests/**/*.py"
---

# Test expectations

Use pytest-homeassistant-custom-component fixtures and synthetic router data.
Mock network I/O, not Home Assistant itself. Cover valid/invalid response
shapes, HTTPS origin validation, authentication, bounded request failures,
duplicates, changed identities, setup/unload/reload, unavailable/recovery,
and privacy-safe diagnostics. Do not use real router secrets or identifiers.
Keep >=96% integration and 100% config-flow coverage; do not exclude production
branches or lower gates to make tests pass. Audit tests must reject incomplete
or unsupported checklist claims and test cumulative tier reporting.
