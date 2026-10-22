# Contributing

## Development baseline

Use Python >=3.14.2,<3.15 and Home Assistant Core 2026.10.1, matching the
reference HAVRV project's Python/HA release family. Direct development
dependencies are pinned in `pyproject.toml`; the Home Assistant pytest
plugin pins additional dependencies. Upgrade the HA and plugin pins together,
review dependency advisories, and use the local checks below as practical.
There are no extra runtime requirements beyond Home Assistant's dependencies.

Install with `python -m pip install -e ".[test]"` in a virtual environment.
The project uses setuptools for packaging; Home Assistant/HACS loads the
`custom_components/cradlepoint` directory directly.

## Local checks

Run relevant checks from the repository root when practical. CI runs the project
gates for contributions:

```sh
ruff check .
ruff format --check .
mypy
pytest
python -m coverage report --include=custom_components/cradlepoint/config_flow.py --fail-under=100
python scripts/quality_scale_audit.py
```

`pytest` requires at least 96% coverage across integration code. The separate
coverage command enforces 100% config-flow coverage. Auditor tests validate
checklist integrity and cumulative tier reporting. CI additionally runs
HACS and hassfest; local lint/type/test success is not a substitute for them.

## Change contract

* Use vendor documentation to guide endpoint and field choices. Automated tests
  with synthetic fixtures are sufficient during development; real-router traces
  are not required. Do not infer modem state from connectivity to the management
  API.
* Use Home Assistant async helpers, its injected web session, typed config-entry
  runtime data, stable serial-based identity, translated names, and a shared
  coordinator. Do not block the event loop or create per-entity polling.
* Test setup/unload, invalid input, authentication loss, connection errors,
  malformed responses, device identity changes, and unavailable/recovery cases.
* Keep HTTPS certificate verification enabled by default. A per-router bypass is
  permitted only with explicit user authorization during integration setup,
  following the warning and isolation requirements in `docs/security.md`.
  Never bypass verification automatically after a certificate failure. Preserve
  HTTPS encryption (including on port 443) and never add HTTP fallback.
  The current implementation has no bypass option; this policy permits a future
  opt-in feature, not a change to existing connection behavior.
  Never follow authentication-bearing redirects, log credentials or raw
  responses, or add write operations implicitly.
* Use synthetic test credentials. Strip IPs, hostnames, serials, IMEI/ICCID,
  location, account IDs, and authorization headers from contributed fixtures.
* Update relevant docs and quality-scale evidence when those are affected.
  Never claim a medallion merely because CI passes.
* Review CI results when available; missing or skipped checks do not count as
  passing results.

## Repository configuration

`.github/copilot-instructions.md` defines coding-agent roles and quality
expectations. `.github/instructions` supplies path-scoped integration and test
guidance. Agent work is held to the same checks as contributor work.
Dependabot proposes Python and pinned GitHub Action updates weekly.
GitHub Actions jobs have read-only repository permissions and pin their action
references to immutable commits. The upstream HACS/hassfest actions still
resolve their own container images; those images are not locked by this
repository. No workflow needs router credentials.

## Maintainer settings

After the first CI run, configure a repository ruleset/branch protection to
require `Lint and types`, `Tests and quality scale`, `HACS validation`,
and `Home Assistant validation` plus review before merge. These GitHub
settings are administrative actions, not applied automatically by this scaffold.
The upstream HACS validator requires a publicly accessible repository and
nonempty repository topics. Publication is an owner decision; never change
visibility automatically or weaken the HACS gate to accommodate a private
repository. Missing raw-file access can appear as misleading manifest errors.
Enable vulnerability alerts and review Dependabot proposals rather than
automatically merging dependency changes.

## Release checklist

Real-hardware validation is optional at this experimental stage; no verified
router traces are required. Update the component manifest, project version, and
changelog together when preparing a release. Review available CI results before
tagging.
HACS custom-repository availability does not imply HACS default-catalog approval
or a Home Assistant quality award.
