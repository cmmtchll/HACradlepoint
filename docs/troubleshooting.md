# Troubleshooting

## Integration is missing from Add integration

Confirm the directory is `custom_components/cradlepoint` under the Home
Assistant configuration directory, not nested inside another copy of the
repository. Restart after installation and check Core is at least 2026.10.1.

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

Confirm the router provides the documented `/api/status/product` response:
`success: true` and a data object with nonempty `serial_number` and
`product_name` strings. HTML login pages, missing identity fields, redirects,
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

## Reporting an issue

Include Home Assistant version, integration version, NCOS version, model,
expected behavior and sanitized error text. Diagnostics are available from
the integration entry and intentionally omit credentials, address and serial.
Do not upload raw API dumps, authorization headers, backups, IMEI/ICCID,
GPS coordinates, or account details. No specific hardware is yet verified.
