#!/bin/bash
# User-run on the target AFTER final paths, venv, units, and trusted TLS pair exist.
set -euo pipefail
python3.12 -B /opt/stillhere/current/deploy/preflight.py
systemd-analyze verify /etc/systemd/system/stillhere-*.service /etc/systemd/system/stillhere-*.timer
runuser -u caddy -- caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
python3.12 -B /opt/stillhere/current/deploy/verify_permissions.py
echo native_validation_ok
