---
applyTo: "custom_components/cradlepoint/**/*.py"
---

# Integration implementation

Use Home Assistant async/config-entry/coordinator conventions and strict types.
Use its injected web session and verified HTTPS without redirects. Normalize
documented API fields and reject malformed identity instead of guessing.
Preserve serial-based entry, device and entity identity when URLs change.
Authentication failures must reach HA reauthentication, while network/schema
failures mark coordinator-backed entities unavailable and retry normally.
Do not log response bodies, credentials or authenticated connection details.
Keep entity names, flow errors and icons translatable. Test full lifecycle,
identity checks, error handling and recovery before changing quality status.
