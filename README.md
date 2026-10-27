# CradlePoint for Home Assistant

[![Validate](https://github.com/cmmtchll/HACradlepoint/actions/workflows/validate.yml/badge.svg)](https://github.com/cmmtchll/HACradlepoint/actions/workflows/validate.yml)

An **experimental, read-only** custom integration for CradlePoint routers using
the router's local NetCloud OS (NCOS) API. This repository follows
[HAVRV](https://github.com/cmmtchll/HAVRV)'s async integration conventions,
documentation, strict typing, coverage gates, and evidence-based quality tracking.
It is not affiliated with Ericsson Enterprise Wireless Solutions.

## Implemented experimental telemetry

- UI setup, serial-number-based duplicate prevention, reauthentication, and
  reconfiguration without changing router identity.
- DHCP discovery for known CradlePoint MAC prefixes, with the detected HTTPS
  address prefilled and local credentials entered by the user.
- One router device, **Product name**, reported **NCOS version**, primary WAN
  and WAN connection state.
- Dynamic per-WAN connection/link states, documented transport type, received/sent
  byte totals and reset-safe average byte/second rates.
- Optional GPS lock, age, coordinates, altitude, speed, heading and satellites.
  A **GPS location** device tracker combines latitude/longitude on the same router
  device for Home Assistant maps and zones, alongside the existing GPS sensors.
  GPS requests are **off by default**; enable deliberately through **Configure**.
  Enabled GPS has an independent 60-second polling stream and position-expiry
  deadlines, so slow WAN/firmware requests cannot delay its updates.
- Local HTTPS polling every 60 seconds, connection validation at setup, and
  unavailable/recovery handling.
- Minimal diagnostics that do not export credentials, router addresses, serial
  numbers, or raw API responses.
- Ruff, strict mypy, pytest with at least **96% integration coverage** and
  **100% config-flow coverage**, HACS validation, hassfest, and a complete
  Bronze-through-Platinum checklist audit.

**Hardware-tested: IBR1700-600M.** User-provided diagnostics confirm successful
setup and a successful latest coordinator update with integration **0.1.0** on
**Home Assistant OS / Core 2026.10.4** (aarch64, Python 3.14.9).
The NCOS firmware version and optional firmware/WAN/GPS readings were not included;
this is not verification of every feature or other models. See
[hardware verification scope](docs/features.md#hardware-verification).
Automated tests use synthetic API responses. A router must provide the documented NCOS
`GET /api/status/product_info` endpoint with `success: true`, nonempty
`data.manufacturing.serial_num` and `data.product_name`. A **404 only** permits
the legacy `/api/status/product` contract. NCOS 6.x/7.x compatibility remains
unverified; optional endpoints are
capability-detected, not guessed from a model/version. Wi-Fi-as-WAN can contribute
generic WAN readings if present in that tree; SSID/signal schemas remain deferred.
WAN state is **not Internet health**. Controls and cloud access are not
implemented. DHCP-based discovery depends on Home Assistant seeing the router
request a lease on its network. See [contracts and limits](docs/features.md).

## Installation

Requires Home Assistant **2026.10.1 or later**; development is tested against
Core 2026.10.1 on Python 3.14. This repository is not in the default HACS catalog
and does not currently publish release assets.

### HACS custom repository

HACS requires a publicly accessible repository; use manual installation if
the repository is private or unavailable to HACS.

1. In HACS, open **Custom repositories**.
2. Add `https://github.com/cmmtchll/HACradlepoint` with category **Integration**.
3. Download **CradlePoint** and restart Home Assistant.
4. Follow [setup](docs/setup.md).

### Manual

1. Download this repository and copy `custom_components/cradlepoint` into
   your Home Assistant configuration directory's `custom_components/`.
2. Restart Home Assistant.
3. Open **Settings → Devices & services → Add integration → CradlePoint**.
4. Enter the router's HTTPS origin and local API username/password.

The router must have a trusted HTTPS certificate matching the configured
hostname. There is **no HTTP mode**. For routers whose certificate cannot be
validated, you may explicitly clear **Verify TLS certificate** during setup;
this keeps HTTPS but removes server authentication. See the
[security guide](docs/security.md) before entering credentials.

## Configuration and removal

The router URL, username, and password are configured through the UI, not YAML.
The polling interval is fixed at 60 seconds. Use **Reconfigure** to update the
address or credentials for the same router; authentication failures prompt
reauthentication. **Configure** offers GPS consent: enabling it exposes precise
location to Home Assistant, history and backups. See [all configuration
parameters](docs/setup.md).

To remove the integration, delete its entry under **Settings → Devices &
services**. Home Assistant unloads its entities and stops polling. Remove the
download from HACS (or delete its component directory) and restart to uninstall.
Deleting the integration does not change the router. Revoke unused router
credentials and protect Home Assistant backups, which may retain configuration.

## Documentation

- [Setup and configuration](docs/setup.md)
- [Supported functions, limitations, and examples](docs/features.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Security and API contract](docs/security.md)
- [Architecture](docs/architecture.md)
- [Contributing and local checks](CONTRIBUTING.md)
- [Quality scale / medallion status](quality_scale.md)
- [Changelog](CHANGELOG.md)

## Quality status

Bronze, Silver, Gold, and Platinum are **targets, not awarded medallions**.
The checklist records all 54 official rules with evidence or explicit gaps.
A green checklist audit validates tracking integrity; it does not prove
device compatibility or award a tier. Branding, discovery assessment, repairs,
and broader real-router feature/firmware verification remain open.
See [quality status](quality_scale.md).

## Development

Use Python `>=3.14.2,<3.15`, then:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[test]"
ruff check .
ruff format --check .
mypy
pytest
python -m coverage report --include=custom_components/cradlepoint/config_flow.py --fail-under=100
python scripts/quality_scale_audit.py
```

See [contributing](CONTRIBUTING.md) for CI expectations and agent guidance.
Released under the [MIT license](LICENSE).
