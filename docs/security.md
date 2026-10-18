# Security and API contract

## Transport and credentials

Only HTTPS origins are accepted. TLS certificate verification remains enabled.
The client uses HTTP Basic authentication to the explicitly configured origin;
it does not follow redirects or accept credentials embedded in a URL.
No HTTP fallback, SSL bypass, cloud API key, write operation, or remote shell
is included. Router credentials must never be stored in repository files or CI.
DHCP discovery is unauthenticated network metadata and only prefills the address;
the user must provide credentials, and the certificate must still validate for
the selected HTTPS origin.

Passwords are stored by Home Assistant in its config-entry storage, not an
external secret manager. Protect that storage and backups, restrict account
permissions where NCOS supports it, and rotate credentials when necessary.
Do not expose the router's management API to the public internet.

## Data minimization

The client retains only normalized allowlisted product/WAN/GPS fields, not
arbitrary response data. Diagnostics remain limited to product name and coordinator
update success: no addresses, credentials, serials, WAN/modem keys, coordinates,
NMEA or raw responses. Logs/errors never interpolate response bodies, identifying
network/modem/location data, authenticated URLs or credentials.

WAN entity IDs and the primary WAN state deliberately use reported device keys;
they may contain modem identifiers, so sanitize registry/state exports too.
GPS is explicit opt-in and is never requested by default. Opting in publishes
precise coordinates as sensor states: Home Assistant dashboards, recorder history,
automations, external state consumers and backups may retain them. Disable the
option to stop GPS requests and unload entities; separately manage existing
history/backups and do not publicly share them. Unlocked/stale positions and raw
NMEA/lastpos are not exported. No passkey sensor or Wi-Fi configuration read exists.

Responses are limited to 4 MiB after decompression and 64 JSON nesting levels;
duplicate JSON members are rejected. Product identity and text sensor values
are limited to Home Assistant's 255-character state bound. WAN device counts
and retained discovery identities are bounded to prevent malformed or continually
changing keys from creating unlimited entities. These are integration resource
limits, not claims about vendor hardware capacity.

## Vendor contract and verification status

Sources:

* [NCOS API overview](https://docs.cradlepoint.com/r/NCOS-SDK-Router-API-for-Applications/NetCloud-OS-API)
* [Product information](https://docs.cradlepoint.com/r/NCOS-SDK-Router-API-for-Applications/Product-Information)
* [Pinned vendor SDK NCOS reference](https://github.com/cradlepoint/sdk-samples/tree/603aa29773a0b8a9bd4bff8c08669439b5cfe6c7/docs/ncos-api)

The client prefers `GET /api/status/product_info`, with a successful JSON envelope
and `manufacturing.serial_num`/`product_name` string fields. Only endpoint absence
(HTTP 404) falls back to the original `/api/status/product`
`serial_number`/`product_name` contract. The serial is checked **before** reading
telemetry on every poll, including the independent opted-in GPS stream.
This is not an atomic binding across separate vendor requests: an address
switching between routers mid-poll remains a limitation.
Optional firmware, WAN and opted-in GPS contracts,
validation and freshness policy are listed in `docs/features.md`.

These documents define the initial contract; they do not substitute for
real-router verification. NCOS 6.x/7.x and IBR1700-600M remain experimental targets;
family/model compatibility and account permissions are unverified.
Tests use invented fixtures with no real
credentials or identifiers.

## Vulnerability reporting

Do not post live credentials or sensitive router data in public issues.
Use GitHub private vulnerability reporting if enabled by the maintainer.
If unavailable, request a private reporting channel without including exploit
details or secrets. See `CONTRIBUTING.md` for maintainer security settings.
