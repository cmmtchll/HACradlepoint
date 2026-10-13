Security and API contract
========================

Transport and credentials
-------------------------

Only HTTPS origins are accepted. TLS certificate verification remains enabled.
The client uses HTTP Basic authentication to the explicitly configured origin;
it does not follow redirects or accept credentials embedded in a URL.
No HTTP fallback, SSL bypass, cloud API key, write operation, or remote shell
is included. Router credentials must never be stored in repository files or CI.

Passwords are stored by Home Assistant in its config-entry storage, not an
external secret manager. Protect that storage and backups, restrict account
permissions where NCOS supports it, and rotate credentials when necessary.
Do not expose the router's management API to the public internet.

Data minimization
-----------------

The client reads product identity only and does not retain arbitrary response
fields. Diagnostics use an allowlist; they omit connection addresses,
credentials, router serial numbers and raw responses. Logs and errors must
not interpolate credentials, authenticated URLs, or raw router payloads.
Future modem/GPS/network telemetry needs a new privacy assessment.

Vendor contract and verification status
--------------------------------------

Sources:

* `NCOS API overview
  <https://docs.cradlepoint.com/r/NCOS-SDK-Router-API-for-Applications/NetCloud-OS-API>`_
* `Product information
  <https://docs.cradlepoint.com/r/NCOS-SDK-Router-API-for-Applications/Product-Information>`_

The foundation expects ``GET /api/status/product`` with a successful JSON
envelope and ``serial_number``/``product_name`` string fields. The configured
router serial is checked on subsequent reads to avoid assigning another
router's identity to the same device.

These documents define the initial contract; they do not substitute for
real-router verification. Supported NCOS versions and account-permission
requirements remain unverified. Tests use invented fixtures with no real
credentials or identifiers.

Vulnerability reporting
----------------------

Do not post live credentials or sensitive router data in public issues.
Use GitHub private vulnerability reporting if enabled by the maintainer.
If unavailable, request a private reporting channel without including exploit
details or secrets. See ``CONTRIBUTING.rst`` for maintainer security settings.
