# Contributing

## Development baseline

Use Python >=3.14.2,<3.15 and Home Assistant Core 2026.10.1, matching the
reference HAVRV project's Python/HA release family. Direct development
dependencies are pinned in `pyproject.toml`; the Home Assistant pytest
plugin pins additional dependencies. Upgrade the HA and plugin pins together,
review dependency advisories, and run every gate before committing.
There are no extra runtime requirements beyond Home Assistant's dependencies.

Install with `python -m pip install -e ".[test]"` in a virtual environment.
The project uses setuptools for packaging; Home Assistant/HACS loads the
`custom_components/cradlepoint` directory directly.

## Required local gates

Run from the repository root:

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

* Verify endpoint fields against vendor documentation and sanitized real-router
  fixtures before adding telemetry. Do not infer modem state from connectivity
  to the management API.
* Use Home Assistant async helpers, its injected web session, typed config-entry
  runtime data, stable serial-based identity, translated names, and a shared
  coordinator. Do not block the event loop or create per-entity polling.
* Test setup/unload, invalid input, authentication loss, connection errors,
  malformed responses, device identity changes, and unavailable/recovery cases.
* Keep HTTPS verification enabled. Never follow authentication-bearing redirects,
  log credentials or raw responses, or add write operations implicitly.
* Use synthetic test credentials. Strip IPs, hostnames, serials, IMEI/ICCID,
  location, account IDs, and authorization headers from contributed fixtures.
* Update relevant docs, `quality_scale.yaml` evidence, and the changelog.
  Never claim a medallion merely because CI passes.
* Inspect the `Validate` workflow for the latest commit. Missing, skipped,
  awaiting-approval, and cancelled checks are unverified, not passing.
  If necessary, dispatch the existing workflow and diagnose its logs.

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
Enable vulnerability alerts and review Dependabot proposals rather than
automatically merging dependency changes.

## Release checklist

Validate on real hardware; record model, NCOS version, certificate setup and
sanitized response shape. Update the component manifest, project version, and
changelog together. Run every CI check for that commit before tagging a release.
HACS custom-repository availability does not imply HACS default-catalog approval
or a Home Assistant quality award.
