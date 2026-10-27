# Troubleshooting

## Integration is missing from Add integration

Confirm the directory is `custom_components/cradlepoint` under the Home
Assistant configuration directory, not nested inside another copy of the
repository. Restart after installation and check Core is at least 2026.10.1.

## HACS installation or validation fails

HACS distribution and its upstream validator require a public repository.
Repository publication and descriptive GitHub topics are maintainer settings,
not integration configuration. If validation reports a missing manifest
dictionary or invalid `hacs.json`, first check whether HACS can retrieve the
files anonymously; do not assume the JSON is malformed. Manual installation
remains available when HACS cannot access the repository. Do not add access
tokens to the integration or skip validation checks.

## Cannot connect

Verify the router URL is an HTTPS origin only, including a custom port if
needed. Test reachability from the Home Assistant host, not only a browser on
another machine. Confirm management access/firewall rules allow that host.
Verify the certificate chain and hostname match. Self-signed certificates
are not accepted unless the issuer is trusted by the Home Assistant runtime.
The integration does not follow redirects; enter the final HTTPS origin.
Do not expose management ports publicly to work around access problems.

## Invalid authentication

Use local router credentials permitted to read the NCOS product endpoint.
NetCloud credentials are not supported. HTTP 401/403 is treated as an
authentication failure; check both credentials and permissions. Complete
reauthentication from the integration entry if a previously configured password
was changed.

## Unsupported or malformed response

Confirm `/api/status/product_info` returns `success: true` and nonempty
`data.manufacturing.serial_num`/`data.product_name` strings. HTTP 404 alone permits
the legacy `/api/status/product` response with `serial_number`/`product_name`.
HTML login pages, missing identity fields, redirects,
and unsuccessful API responses are not accepted as working connections.
Provide a sanitized response shape when reporting an incompatible firmware.

## Already configured or different router

Entries are unique by serial, not by hostname. Reconfiguration and
reauthentication cannot substitute another physical router. Add a new entry
for a replacement, and remove the old entry if no longer needed.

## Sensor unavailable

The coordinator marks the entity unavailable after failed updates and retries
on its normal polling schedule. Correct the router/network/certificate issue,
or complete reauthentication when requested. The last product name is not
presented as a current reading while the router is unavailable.

Optional telemetry failures affect only the corresponding capability. HTTP
404/501 may mean unsupported firmware or a disabled capability; later polls retry.
Any endpoint's HTTP 401/403 requests reauthentication. Missing per-WAN counters
show unknown, not zero; rates need two consecutive good samples and become unknown
after resets/outages. WAN state is not a test of Internet reachability.
GPS entities require the **Configure** opt-in; coordinates also need a locked fix
with age plus elapsed delivery time below 120 seconds. Positions expire without
waiting for another poll. GPS has its own 60-second schedule, independent of
WAN/firmware response delays. Check the router's antenna/GPS settings
without posting NMEA or location. Wi-Fi SSID/signal fields are deliberately deferred
because the verified vendor schema does not specify them.

## Reporting an issue

Include Home Assistant version, integration version, NCOS version, model,
expected behavior and sanitized error text. Diagnostics are available from
the integration entry and intentionally omit credentials, address and serial.
Do not upload raw API dumps, authorization headers, backups, IMEI/ICCID,
GPS coordinates, or account details. Basic operation is hardware-verified on
the IBR1700-600M; see [verification scope](features.md#hardware-verification)
before assuming a firmware version or optional feature has been tested.
