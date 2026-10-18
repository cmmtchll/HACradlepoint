# Setup and configuration

## Prerequisites

* Home Assistant Core 2026.10.1 or later and this custom integration installed
  through a HACS custom repository or by copying its component directory.
* A CradlePoint router exposing the documented local NCOS product endpoint.
  Model and firmware compatibility have not been verified on real hardware.
* Network access from the Home Assistant host to the router's HTTPS management
  service. NetCloud account credentials and cloud API keys are not used.
* A trusted certificate whose DNS/IP subject matches the configured address.
  Configure a publicly trusted certificate or an appropriate private CA trust
  chain in the Home Assistant runtime; the integration cannot import a CA.
  A default self-signed router certificate will fail verification.
* Local credentials permitted to read `/api/status/product_info` and applicable
  optional status endpoints (or the legacy `/api/status/product`). Use the
  least-privileged account supported by your router's NCOS release.

## Installation and onboarding

Follow the HACS/manual instructions in the root README. Restart Home Assistant
after installing the component, then choose **Settings → Devices & services →
Add integration → CradlePoint**.

Home Assistant may also show a discovered CradlePoint router when it observes
the router request a DHCP lease and its MAC address matches a known CradlePoint
prefix. Discovery prefills the HTTPS origin; you must still enter local API
credentials and the router must have a trusted certificate matching that
address. DHCP discovery is not authentication, and routers that do not request
a lease visible to Home Assistant must be added manually.

## Configuration parameters

### Router URL

The HTTPS origin, for example `https://router.example.test` or
`https://router.example.test:8443`. Do not include `/api`, a username,
password, query string, or fragment. A trailing slash is normalized.
The example hostname is reserved for documentation and is not a real router.

### Username

Your local router API account name, not a NetCloud email address.

### Password

The account's password. It is stored in the Home Assistant config entry
and backups; diagnostics do not include it.

There are no YAML configuration parameters or options for polling or TLS.
Polling is fixed at 60 seconds with a bounded request timeout. The setup flow
tests the endpoint and requires a product name and serial number before it
creates an entry. The serial prevents configuring the same router twice.

### GPS telemetry (Configure option, default off)

Open the configured entry's **Configure** dialog and enable **GPS location
telemetry** only if you consent to precise location becoming available to
Home Assistant and its history/backups. No GPS request is made while disabled.
Saving options reloads the entry. Disabling unloads location entities and stops
GPS reads, but does not erase historical states or backups.
See [GPS freshness and units](features.md#gps-consent-and-freshness).

## Changing configuration

Use the entry's **Reconfigure** flow to update the address or credentials.
The new connection must return the existing router serial; a different router
requires its own entry. Following an authentication failure, complete Home
Assistant's reauthentication flow. Credential changes reload the integration.

## Removal

Delete the entry in **Settings → Devices & services** to unload entities and
stop scheduled polling. Remove the HACS download or component directory and
restart to uninstall. The integration does not modify router configuration.
Revoke unused API credentials. Old backups may still contain config entries.
