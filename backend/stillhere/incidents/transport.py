"""Small credential-free GET transport with fixed hosts, deadlines and byte limits."""

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

HOSTS = {"api.weather.gov", "earthquake.usgs.gov", "www.fema.gov"}
MAX_BYTES = 1024 * 1024


class SourceFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def approved_url(url):
    parsed = urlsplit(url)
    return (parsed.scheme == "https" and parsed.hostname in HOSTS and parsed.port in (None, 443)
            and not parsed.username and not parsed.password)


class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not approved_url(newurl) or urlsplit(newurl).hostname != urlsplit(req.full_url).hostname:
            raise SourceFailure("source_redirect_rejected")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class PublicJSONTransport:
    def __init__(self, opener=None):
        # Never inherit proxy credentials or attach AWS/household authentication.
        self.opener = opener or build_opener(ProxyHandler({}), OfficialRedirect())

    def get_json(self, url, deadline):
        if not approved_url(url):
            raise SourceFailure("source_url_rejected")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SourceFailure("source_timeout")
        request = Request(url, headers={"User-Agent": "StillHere/0.1 incident-context",
                                       "Accept": "application/geo+json, application/json"})
        try:
            with self.opener.open(request, timeout=min(6, remaining)) as response:
                if time.monotonic() >= deadline:
                    raise SourceFailure("source_timeout")
                if response.status == 204:
                    return {"type": "FeatureCollection", "features": []}
                chunks, size = [], 0
                while True:
                    if time.monotonic() >= deadline:
                        raise SourceFailure("source_timeout")
                    chunk = response.read(min(16384, MAX_BYTES + 1 - size))
                    if time.monotonic() >= deadline:
                        raise SourceFailure("source_timeout")
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise SourceFailure("source_response_limit")
                def invalid_constant(value):
                    raise ValueError("Non-finite value")
                def unique_object(pairs):
                    result = {}
                    for key, value in pairs:
                        if key in result:
                            raise ValueError("Duplicate JSON key")
                        result[key] = value
                    return result
                return json.loads(b"".join(chunks), parse_constant=invalid_constant, object_pairs_hook=unique_object)
        except SourceFailure:
            raise
        except HTTPError as error:
            code = "source_rate_limited" if error.code == 429 else "source_http_error"
            error.close()
            raise SourceFailure(code) from None
        except (TimeoutError, URLError, OSError):
            raise SourceFailure("source_timeout_or_network") from None
        except (ValueError, UnicodeError, RecursionError):
            raise SourceFailure("source_invalid_response") from None
