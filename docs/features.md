# Features, limitations, and examples

## Supported devices

No specific router model or NCOS firmware version has been hardware-verified.
The IBR1700-600M and NCOS 6.x/7.x are experimental targets. There is no hard-coded
model or firmware gate and no claim that these are fully supported or that a
particular model receives both firmware families. The version sensor reports
the actual documented firmware components. The identity contract is local HTTPS
`GET /api/status/product_info`, `success: true`, and nonempty
`data.manufacturing.serial_num`/`data.product_name`. Only a 404 on this endpoint
permits the legacy `/api/status/product` string fields
`data.serial_number`/`data.product_name`. Invalid schema, redirects, TLS/auth
failures and other statuses never trigger identity fallback.
Synthetic fixtures are sufficient for development, not proof of hardware support.

## Supported functions and updates

One device is created for each configured serial number, independent of address.
One shared 60-second coordinator cycle checks identity first, then requests
firmware/WAN capabilities concurrently. Enabled GPS uses a separate identity-first
60-second coordinator, so unrelated requests cannot delay its scheduled updates
or entity publication. Requests use verified HTTPS, no redirects and a 10-second
timeout each. No entity makes its own request.

| Sensors | Documented source | Units/behavior |
| --- | --- | --- |
| Product name | `/api/status/product_info` | Required identity |
| NCOS version | `/api/status/fw_info` | Integer major/minor/patch components |
| Primary WAN | `/api/status/wan/primary_device` | Reported device key |
| WAN connection state | `/api/status/wan/connection_state` | Connected/disconnected/connecting, not Internet health |
| Per-WAN connection and link state | `/api/status/wan/devices`, `status` | Connected/disconnected/connecting; up/down/unknown |
| Per-WAN transport | Same tree, `info.type` | Only documented `mdm`/`ethernet`; unknown types remain unknown |
| Per-WAN received/sent totals | Same tree, `stats.in`/`stats.out` | Nonnegative integer bytes, HA total-increasing statistics |
| Per-WAN receive/send rates | Consecutive totals and monotonic sample time | Bytes/second average between polls |
| Optional GPS | `/api/status/gps`, `fix` | Lock, age seconds, decimal latitude/longitude degrees, altitude meters, speed knots, heading degrees, satellites |

New WAN keys discovered after setup create stable serial-plus-device-key entities.
Removed devices become unavailable without deleting registry/history identity;
returning keys reuse their entities. Key prefixes are never used to infer
transport. The client does not retain unrecognized fields or export raw attributes.
Malformed individual devices are omitted without hiding healthy devices. Invalid
top-level trees or more than 64 WAN members reject the WAN capability. Discovery
admits at most 64 WAN identities per entry, reserving that budget using existing
registry identities across reloads. Returning admitted keys reuse their entities;
new keys beyond the budget are not added. These are defensive integration limits,
not a hardware compatibility statement. Review unexpected key churn before
removing obsolete registry records to release their reserved budget.

The first rate is unknown. A decreasing counter/reset, missing reading, missing
device, failed WAN read or failed router poll resets the rate baseline: no negative
rate, fabricated zero or bridging an outage. A genuinely unchanged counter yields
zero rate. These are averages, not instantaneous link throughput.
The monotonic sample time is captured when each WAN read completes, independently
of firmware, primary-WAN, connection-state or GPS request latency.

Optional HTTP 404/501, network and schema errors make the affected capability
unavailable while product/other capabilities continue. Missing individual
per-WAN readings remain unknown. Endpoint capabilities are retried on later
cycles, permitting recovery or late enablement. Any endpoint's 401/403 triggers
reauthentication. Failed required product reads or changed serial make the
affected stream's entities unavailable; GPS performs its own identity check
independently of router telemetry. Identity is validated before requests, not
atomically across separate vendor endpoints; mid-poll address failover remains
an architectural limitation.

### GPS consent and freshness

GPS is off by default: no GPS request or GPS entity is created until enabled
through the translated **Configure** options flow. Options changes reload the
entry. Disabling immediately redacts GPS states and stops further GPS requests,
including if the subsequent unload fails; successful reload unloads GPS entities.
An in-flight result cannot publish coordinates after consent is revoked.
Existing recorder history, entity registry records and backups are not erased.

Coordinates require a locked fix with a finite, nonnegative age. Reported age
plus elapsed request/processing time must remain **below 120 seconds**.
Positions expire at that deadline even if the next request stalls. This is an
integration freshness policy, not a vendor guarantee.
Unlocked, missing-age or older fixes have unavailable position/motion
readings; `lastpos` is deliberately ignored. Numeric/string DMS components are
validated and converted with South/West signs, including negative zero.
Latitude/longitude ranges, nonnegative speed, heading [0,360), integer satellite
counts and finite values are checked. Missing data is never synthesized as zero;
a real zero in a valid fresh locked fix remains valid. Location is updated on the
independent 60-second schedule, not continuously or for navigation/safety
applications. GPS request/schema failures make GPS unavailable and are retried;
lock recovery restores valid positions without restarting the integration.
LAN GPS/NMEA streaming and dual-source failover are not implemented pending
hardware and source-trust verification.

The API being reachable is not evidence that the WAN has internet access.
No integration-specific service actions, triggers, or conditions are provided.
Standard Home Assistant entity state triggers/conditions can still be used.
There are no router configuration changes, reboot actions, or switch controls.

## Use cases

* Inventory a router's reported product model in Home Assistant.
* Observe management-API availability through the entity's unavailable state.
* Monitor documented WAN link/state changes without claiming Internet health.
* Track per-WAN traffic usage and polling-interval average rates.
* Deliberately opt into router GPS display, subject to privacy/freshness limits.

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

Modem/SIM identity/details, cellular signal, uptime, NetCloud cloud APIs,
automatic router discovery and all write controls are deferred.
The vendor `/api/status/wwan` documentation calls device entry fields “varies”:
no exact SSID/signal contract is established. It is not requested or guessed.
Wi-Fi-as-WAN generic statistics/state work only if exposed in the documented WAN
tree; Wi-Fi SSID, signal, passkeys and Wi-Fi management are not exposed.
HTTPS verification cannot be disabled, so factory self-signed
certificates require certificate/trust configuration before onboarding.
Discovery and repairs remain quality-checklist gaps. No quality medallion
has been awarded.

Adding telemetry requires verified endpoint contracts, typed unit-aware
parsing, lifecycle/error tests, privacy review, updated documentation, and
reassessment of applicable quality rules.

## Pinned vendor references

The experimental contracts use the public vendor
[NCOS API reference](https://github.com/cradlepoint/sdk-samples/tree/603aa29773a0b8a9bd4bff8c08669439b5cfe6c7/docs/ncos-api):
`status/product_info.md`, `status/fw_info.md`,
`status/wan/devices/{info,status,stats}.md`,
`status/wan/{primary_device,connection_state}.md`,
`status/gps.md`, `status/gps/fix.md`, and `status/wwan.md`.
These documentation-guided synthetic tests do not establish a compatibility
matrix for either NCOS family, the latest vendor releases or IBR1700-600M hardware.
