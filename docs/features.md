# Features, limitations, and examples

## Supported devices

No specific router model or NCOS firmware version has been hardware-verified.
The initial API contract is a local HTTPS `GET /api/status/product` returning
`success: true` with nonempty `data.serial_number` and `data.product_name`.
Synthetic fixtures exercise this contract, not manufacturer compatibility.
Contribute sanitized fixtures with model and firmware information before
extending the supported-device matrix.

## Supported functions and updates

The integration creates one device for each configured serial number and a
diagnostic **Product name** sensor. It shares one 60-second coordinator poll
between entities. Device identity is independent of the router's address.
Failed polls make the entity unavailable; a subsequent successful poll restores
it. An API authentication error requests reauthentication.

The API being reachable is not evidence that the WAN has internet access.
No integration-specific service actions, triggers, or conditions are provided.
Standard Home Assistant entity state triggers/conditions can still be used.
There are no router configuration changes, reboot actions, or switch controls.

## Use cases

* Inventory a router's reported product model in Home Assistant.
* Observe management-API availability through the entity's unavailable state.
* Establish an independently tested base for future read-only telemetry.

## Example: alert when the management API becomes unavailable

Replace the illustrative entity ID below with the actual entity ID from
Home Assistant. Product-name entity IDs depend on registry naming/user changes.
An outage alert also covers TLS, authentication, response-schema, and network
errors; it does not identify the cause or prove a cellular/WAN outage.

```yaml
alias: Router management API unavailable
triggers:
  - trigger: state
    entity_id: sensor.cradlepoint_product_name
    to: "unavailable"
    for: "00:05:00"
actions:
  - action: persistent_notification.create
    data:
      title: Router monitoring unavailable
      message: Check the router, credentials, certificate, and local network.
```

## Known limitations and future scope

WAN connectivity, modem/SIM details, cellular signal, traffic counters, uptime,
GPS, NetCloud cloud APIs, automatic discovery, and write controls are not
implemented. HTTPS verification cannot be disabled, so factory self-signed
certificates require certificate/trust configuration before onboarding.
Discovery and repairs remain quality-checklist gaps. No quality medallion
has been awarded.

Adding telemetry requires verified endpoint contracts, typed unit-aware
parsing, lifecycle/error tests, privacy review, updated documentation, and
reassessment of applicable quality rules.
