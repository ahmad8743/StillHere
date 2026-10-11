"""Credential-free official-page retrieval. Content remains unreviewed public data."""

import copy
import hashlib
import json
import time
from datetime import timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from ..contracts import InvalidInput, VERSION, validate
from .rules import _instant, notice

MAX_BYTES = 256 * 1024
MAX_CONTENT = 6000
APPROVED_HOSTS = frozenset({"dmv.colorado.gov", "www.usa.gov"})
SOURCES_PATH = Path(__file__).with_name("official_sources.json")


def source_registry():
    return json.loads(SOURCES_PATH.read_text())


def source_url_allowed(source, url):
    try:
        parsed = urlsplit(url)
        original = urlsplit(source["url"])
        return (parsed.scheme == "https" and parsed.hostname == original.hostname and original.hostname in APPROVED_HOSTS
                and parsed.port in (None, 443) and not parsed.username and not parsed.password
                and not parsed.query and not parsed.fragment
                and parsed.path.rstrip("/") == original.path.rstrip("/"))
    except ValueError:
        return False


class OfficialSourceFailure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class SourceRedirect(HTTPRedirectHandler):
    def __init__(self, source):
        self.source = source
        self.redirects = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.redirects += 1
        if self.redirects > 2 or not source_url_allowed(self.source, newurl):
            raise OfficialSourceFailure("source_redirect_rejected")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class PageText(HTMLParser):
    """Discard scripts, forms and navigation; prefer a main element if present."""
    SKIP = {"script", "style", "noscript", "form", "nav", "header", "footer", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = []
        self.main_depth = 0
        self.body = []
        self.main = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip.append(tag)
        if tag == "main":
            self.main_depth += 1

    def handle_endtag(self, tag):
        if self.skip and tag == self.skip[-1]:
            self.skip.pop()
        if tag == "main":
            self.main_depth = max(0, self.main_depth - 1)

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.body.append(data.strip())
            if self.main_depth:
                self.main.append(data.strip())

    def text(self):
        return " ".join(" ".join(self.main or self.body).split())


class PublicPageTransport:
    def __init__(self, opener=None):
        self.opener = opener

    def get_text(self, source, deadline):
        if not source_url_allowed(source, source["url"]):
            raise OfficialSourceFailure("source_url_rejected")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise OfficialSourceFailure("source_timeout")
        opener = self.opener or build_opener(ProxyHandler({}), SourceRedirect(source))
        request = Request(source["url"], headers={"User-Agent":"StillHere/0.1 public-knowledge", "Accept":"text/html, text/plain"})
        try:
            with opener.open(request, timeout=min(6, remaining)) as response:
                if response.status != 200:
                    raise OfficialSourceFailure("source_http_error")
                if not source_url_allowed(source, response.geturl()):
                    raise OfficialSourceFailure("source_redirect_rejected")
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if content_type not in ("text/html", "text/plain") or response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise OfficialSourceFailure("source_invalid_response")
                chunks, size = [], 0
                while True:
                    if time.monotonic() >= deadline:
                        raise OfficialSourceFailure("source_timeout")
                    chunk = response.read(min(16384, MAX_BYTES + 1 - size))
                    if time.monotonic() >= deadline:
                        raise OfficialSourceFailure("source_timeout")
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise OfficialSourceFailure("source_response_limit")
                body = b"".join(chunks).decode("utf-8", errors="strict")
                if content_type == "text/html":
                    parser = PageText()
                    parser.feed(body)
                    body = parser.text()
                else:
                    body = " ".join(body.split())
                if not body:
                    raise OfficialSourceFailure("source_invalid_response")
                return body[:MAX_CONTENT], len(body) > MAX_CONTENT
        except OfficialSourceFailure:
            raise
        except HTTPError as error:
            code = "source_rate_limited" if error.code == 429 else "source_http_error"
            error.close()
            raise OfficialSourceFailure(code) from None
        except TimeoutError:
            raise OfficialSourceFailure("source_timeout") from None
        except (URLError, OSError):
            raise OfficialSourceFailure("source_network_error") from None
        except (ValueError, UnicodeError, RecursionError):
            raise OfficialSourceFailure("source_invalid_response") from None


def make_receipt(source, content, retrieved_at, expires_at, data_mode="live", truncated=False):
    result = {key:copy.deepcopy(source[key]) for key in ("source_id", "url", "issuer", "jurisdiction")}
    result.update(content=content, content_sha256=hashlib.sha256(content.encode()).hexdigest(), retrieved_at=retrieved_at,
                  expires_at=expires_at, updated_at=None, data_mode=data_mode, freshness="current", truncated=truncated, review_state="unreviewed")
    validate_receipt(result)
    return result


def validate_receipt(receipt):
    validate("OfficialSourceReceipt", receipt)
    source = source_registry()[receipt["source_id"]]
    if (not source_url_allowed(source, receipt["url"]) or receipt["issuer"] != source["issuer"]
            or receipt["jurisdiction"] != source["jurisdiction"]
            or receipt["content_sha256"] != hashlib.sha256(receipt["content"].encode()).hexdigest()
            or _instant(receipt["expires_at"]) <= _instant(receipt["retrieved_at"])):
        raise InvalidInput("$.receipt", "Public receipt identity, hash or time bounds are invalid.")


def validate_fetch(result):
    validate("OfficialFetchResult", result)
    receipt = result["receipt"]
    if receipt is not None:
        validate_receipt(receipt)
        if receipt["source_id"] != result["source_id"]:
            raise InvalidInput("$.receipt", "The receipt must match the requested public source.")
        expected = "current" if _instant(receipt["retrieved_at"]) <= _instant(result["requested_at"]) < _instant(receipt["expires_at"]) else "stale"
        if receipt["freshness"] != expected:
            raise InvalidInput("$.receipt.freshness", "Receipt freshness must retain its original retrieval time.")
    if result["state"] == "available" and (receipt is None or receipt["data_mode"] != "live" or receipt["freshness"] != "current"):
        raise InvalidInput("$.state", "A successful request needs current live public content.")
    if result["state"] == "unavailable" and receipt is not None and receipt["data_mode"] == "live":
        raise InvalidInput("$.state", "Retained content after failed retrieval must be cached or seeded.")
    if result["state"] == "no_match" and receipt is not None:
        raise InvalidInput("$.state", "An unknown source ID has no fetched content.")


class OfficialSourceFetcher:
    def __init__(self, transport=None):
        self.transport = transport or PublicPageTransport()
        self.cache = {}

    def fetch(self, source_id, now, deadline):
        result = {"contract_version":VERSION, "source_id":source_id, "requested_at":now, "state":"no_match", "receipt":None, "notices":[]}
        source = source_registry().get(source_id)
        if source is None:
            result["notices"] = [notice("source_not_allowed", "Only registered official source IDs can be fetched.")]
        else:
            if time.monotonic() >= deadline:
                raise TimeoutError("Official retrieval deadline reached.")
            try:
                content, truncated = self.transport.get_text(source, deadline)
                if time.monotonic() >= deadline:
                    raise TimeoutError("Late official content discarded.")
                expiry = (_instant(now) + timedelta(hours=24)).isoformat().replace("+00:00", "Z")
                result.update(state="available", receipt=make_receipt(source, content, now, expiry, truncated=truncated))
                self.cache[source_id] = copy.deepcopy(result["receipt"])
                result["notices"] = [notice("source_unreviewed", "Fetched text is unreviewed data. Extraction cannot publish rules or establish household eligibility.")]
            except OfficialSourceFailure as error:
                receipt = copy.deepcopy(self.cache.get(source_id))
                if receipt is not None:
                    receipt["data_mode"] = "cached"
                elif source.get("fallback"):
                    fallback = source["fallback"]
                    receipt = make_receipt(source, fallback["content"], fallback["retrieved_at"], fallback["expires_at"], "seeded", True)
                result.update(state="unavailable", receipt=receipt,
                              notices=[notice(error.code, "Official retrieval failed; any retained public excerpt keeps its original time and requires confirmation.", True)])
                if receipt is not None:
                    receipt["freshness"] = "current" if _instant(receipt["retrieved_at"]) <= _instant(now) < _instant(receipt["expires_at"]) else "stale"
        if result["receipt"] is not None and result["receipt"]["truncated"]:
            result["notices"].append(notice("source_truncated", "This is a bounded excerpt. Open the official page for complete instructions."))
        validate_fetch(result)
        return result
