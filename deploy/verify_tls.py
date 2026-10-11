"""Verify public CA trust, IP SAN, expiry and deployed health with normal TLS."""
import argparse
import hashlib
import json
import socket
import ssl
import sys
import time
from urllib.request import ProxyHandler, HTTPRedirectHandler, build_opener


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        return None


def check(host="172.238.189.78", port=443, minimum_hours=48):
    context = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=10) as raw:
        with context.wrap_socket(raw, server_hostname=host) as secure:
            cert = secure.getpeercert()
            fingerprint = hashlib.sha256(secure.getpeercert(binary_form=True)).hexdigest()
    if ("IP Address", host) not in cert.get("subjectAltName", ()):
        raise ValueError("IP SAN required")
    expires = ssl.cert_time_to_seconds(cert["notAfter"])
    if expires - time.time() < minimum_hours * 3600:
        raise ValueError("Certificate approaching expiry")
    lifetime = expires - ssl.cert_time_to_seconds(cert["notBefore"])
    if not 0 < lifetime <= 7 * 86400:
        raise ValueError("Expected short-lived certificate")
    with build_opener(ProxyHandler({}), NoRedirect()).open(f"https://{host}:{port}/health", timeout=10) as response:
        body = json.loads(response.read(16384))
        if response.status != 200 or body.get("status") != "ok" or body.get("contract_version") != "0.1":
            raise ValueError("Health failed")
    return {"status": "tls_health_ok", "certificate_sha256": fingerprint,
            "not_after": cert["notAfter"], "remaining_hours": int((expires-time.time())/3600)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="172.238.189.78")
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.host), sort_keys=True))
    except Exception:
        sys.exit("tls_health_failed")
