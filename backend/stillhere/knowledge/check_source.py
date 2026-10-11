"""Credential-free diagnosis using the same bounded public-page transport.

Print only fixed failure categories, HTTP status and extraction counts. Never
load environment files, call a model, persist case data or print response text.
"""

import argparse
import json
import socket
import ssl
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener

from .official import OfficialSourceFailure, PublicPageTransport, SourceRedirect, source_registry

FAILURE_CODES = frozenset({
    "source_url_rejected", "source_redirect_rejected", "source_timeout",
    "source_http_error", "source_rate_limited", "source_invalid_response",
    "source_response_limit", "source_network_error",
})


def network_reason(error):
    cause = error.reason if isinstance(error, URLError) else error
    if isinstance(cause, socket.gaierror):
        return "dns_error"
    if isinstance(cause, ssl.SSLError):
        return "tls_error"
    if isinstance(cause, TimeoutError):
        return "timeout"
    if isinstance(cause, ConnectionRefusedError):
        return "connection_refused"
    if isinstance(cause, ConnectionResetError):
        return "connection_reset"
    return "network_error"


def safe_http_status(value):
    return value if type(value) is int and 100 <= value <= 599 else None


class DiagnosticOpener:
    def __init__(self, source, delegate=None):
        self.delegate = delegate or build_opener(ProxyHandler({}), SourceRedirect(source))
        self.details = {}

    def open(self, request, timeout):
        try:
            response = self.delegate.open(request, timeout=timeout)
            status = safe_http_status(response.status)
            if status is not None:
                self.details["http_status"] = status
            return response
        except HTTPError as error:
            status = safe_http_status(error.code)
            if status is not None:
                self.details["http_status"] = status
            self.details["reason"] = "http_error"
            raise
        except (URLError, OSError) as error:
            self.details["reason"] = network_reason(error)
            raise


def check_source(source_id, timeout=10, delegate=None):
    if type(timeout) is not int or not 1 <= timeout <= 30:
        raise ValueError("Diagnostic timeout must be 1 to 30 seconds.")
    source = source_registry().get(source_id)
    if source is None:
        raise ValueError("Choose a registered public source ID.")
    opener = DiagnosticOpener(source, delegate)
    started = time.monotonic()
    result = {"state": "unavailable"}
    try:
        content, truncated = PublicPageTransport(opener).get_text(source, started + timeout)
        result.update(state="available", extracted_characters=len(content), truncated=truncated)
    except OfficialSourceFailure as error:
        code = error.code if error.code in FAILURE_CODES else "source_unknown_error"
        result["code"] = code
        if code == "source_timeout":
            opener.details["reason"] = "timeout"
    result.update(opener.details, elapsed_seconds=round(time.monotonic() - started, 3))
    return result


def main():
    parser = argparse.ArgumentParser(description="Diagnose an approved public source; no credentials or model calls")
    parser.add_argument("--source-id", choices=tuple(source_registry()), default="source_rule_co_renewal")
    parser.add_argument("--timeout", type=int, default=10, help="Total cooperative deadline, 1 to 30 seconds (default: 10)")
    args = parser.parse_args()
    if not 1 <= args.timeout <= 30:
        parser.error("--timeout must be 1 to 30 seconds")
    result = check_source(args.source_id, args.timeout)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["state"] == "available" else 1


if __name__ == "__main__":
    raise SystemExit(main())
