"""Read-only, versioned public referrals. Capacity and household eligibility stay unknown."""

import copy
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from ..contracts import InvalidInput, VERSION, canonical_json, utc_now, validate
from ..incidents.geography import validate_geography

CATALOG_PATH = Path(__file__).with_name("catalog.json")
MAX_ITEMS = 5
NEED_KINDS = ("shelter", "food_water", "health_support", "transport", "lost_documents",
              "aid_applications", "managing_money")
SOURCE_HOSTS = {"www.usa.gov", "www.211colorado.org"}


def _instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def query_identity(query):
    return copy.deepcopy(query)


def build_query(snapshot, arguments):
    validate("ResourceToolArguments", arguments)
    scope = arguments["location_scope"]
    fact = snapshot["facts"].get(scope + "_location", {})
    geography, geography_state = {}, "unknown"
    if fact.get("state") in ("user_reported", "source_supported") and isinstance(fact.get("value"), dict):
        geography = {key: copy.deepcopy(fact["value"][key]) for key in
                     ("place", "postal_code", "latitude", "longitude", "state", "county_fips") if key in fact["value"]}
        try:
            validate_geography(geography)
            geography_state = "reported" if geography else "unknown"
        except InvalidInput:
            geography, geography_state = {}, "invalid"
    # Corrections to requested_needs take precedence over retained historical need records.
    fact = snapshot["facts"].get("requested_needs", {})
    needs, needs_state = [], "unknown"
    if fact.get("state") in ("user_reported", "source_supported") and fact.get("value") is not None:
        value = fact["value"]
        if isinstance(value, list) and value and all(kind in NEED_KINDS for kind in value):
            needs, needs_state = sorted(set(value)), "reported"
        else:
            needs_state = "invalid"
    query = {"location_scope": scope, "geography": geography, "geography_state": geography_state,
             "need_kinds": needs, "needs_state": needs_state}
    validate("ResourceQuery", query)
    return query


def notice(code, message):
    return {"code": code, "message": message, "retryable": False}


def _public_url(value):
    try:
        parsed = urlsplit(value)
        approved = (parsed.scheme == "https" and parsed.hostname in SOURCE_HOSTS and not parsed.username
                    and not parsed.password and parsed.port in (None, 443))
    except ValueError:
        approved = False
    if not approved:
        raise InvalidInput("$.sources.url", "Use an approved public referral URL.")


def _validate_records(items, sources):
    ids = {source["id"] for source in sources}
    if len(ids) != len(sources) or len({item["id"] for item in items}) != len(items):
        raise InvalidInput("$.resources", "Resource and source identities must be unique.")
    for source in sources:
        _public_url(source["url"])
        if _instant(source["expires_at"]) <= _instant(source["reviewed_at"]):
            raise InvalidInput("$.sources.expires_at", "Referral review expiry must follow its review time.")
    for item in items:
        _public_url(item["contact"]["url"])
        if not item["source_ids"] or not set(item["source_ids"]) <= ids:
            raise InvalidInput("$.items.source_ids", "Each resource must reference returned catalog sources.")
        if any(source["url"] != item["contact"]["url"] for source in sources if source["id"] in item["source_ids"]):
            raise InvalidInput("$.items.contact", "The contact must match its reviewed referral source.")
        if any(source["scope"] != item["coverage"] for source in sources if source["id"] in item["source_ids"]):
            raise InvalidInput("$.items.coverage", "Coverage must match the reviewed source scope.")


def validate_result(result):
    """Cross-record checks supplement the shared structural schemas."""
    validate("ResourceSearchResult", result)
    query = result["search"]["query"]
    validate_geography(query["geography"])
    _validate_records(result["items"], result["sources"])
    if any(not source["id"].startswith("source_resource_") for source in result["sources"]):
        raise InvalidInput("$.sources.id", "Resource result source IDs must use their own namespace.")
    if {source["id"] for source in result["sources"]} != {identifier for item in result["items"] for identifier in item["source_ids"]}:
        raise InvalidInput("$.sources", "Returned attribution must match the retained referrals.")
    for item in result["items"]:
        if item["coverage"]["state"] is not None and (query["geography_state"] != "reported"
                or item["coverage"]["state"] != query["geography"].get("state")):
            raise InvalidInput("$.items.coverage", "Local referrals must match the reported state.")
        if query["need_kinds"] and not set(item["need_kinds"]) & set(query["need_kinds"]):
            raise InvalidInput("$.items.need_kinds", "Referrals must match the requested needs.")
    if result["state"] == "no_match" and result["items"]:
        raise InvalidInput("$.state", "A no-match result cannot contain resources.")
    if result["state"] == "available" and not result["items"]:
        raise InvalidInput("$.state", "An available catalog result must contain referrals.")
    if result["state"] == "unavailable" and (result["items"] or result["sources"]):
        raise InvalidInput("$.state", "Failed catalog lookup cannot supply fresh referrals.")


class ResourceCatalog:
    def __init__(self, loader=None, clock=utc_now):
        self.loader = loader or self._load
        self.clock = clock

    @staticmethod
    def _load():
        # Only this tracked, public, non-secret asset is read. No runtime path or fetch URL.
        return json.loads(CATALOG_PATH.read_text())

    def collect(self, query, input_case_version, deadline=None):
        validate("ResourceQuery", query)
        validate_geography(query["geography"])
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("Resource lookup deadline reached.")
        now = self.clock()
        search = {"query": copy.deepcopy(query), "input_case_version": input_case_version,
                  "retrieved_at": now, "catalog_version": None, "freshness": "unknown", "truncated": False}
        result = {"contract_version": VERSION, "state": "unavailable", "items": [], "sources": [],
                  "search": search, "notices": []}
        try:
            catalog = self.loader()
            validate("ReviewedResourceCatalog", catalog)
            # Validate the entire catalog, including records outside this query's scope.
            _validate_records(catalog["items"], catalog["sources"])
        except (OSError, ValueError, TypeError):
            result["notices"] = [notice("resource_catalog_unavailable", "The reviewed referral catalog is unavailable. Previous saved referrals remain retained; this failure does not establish no local help.")]
            validate_result(result)
            return result
        search["catalog_version"] = catalog["version"]
        items = [copy.deepcopy(item) for item in catalog["items"]
                 if (item["coverage"]["state"] is None or (query["geography_state"] == "reported"
                     and item["coverage"]["state"] == query["geography"].get("state")))
                 and (not query["need_kinds"] or set(item["need_kinds"]) & set(query["need_kinds"]))]
        search["truncated"] = len(items) > MAX_ITEMS
        items = items[:MAX_ITEMS]
        source_ids = {identifier for item in items for identifier in item["source_ids"]}
        source_map = {}
        for source in catalog["sources"]:
            if source["id"] not in source_ids:
                continue
            old_id = source["id"]
            source = copy.deepcopy(source)
            source["id"] = "source_resource_" + hashlib.sha256(canonical_json(
                [query["location_scope"], catalog["version"], old_id]).encode()).hexdigest()[:32]
            source["freshness"] = ("current" if _instant(source["reviewed_at"]) <= _instant(now)
                                   < _instant(source["expires_at"]) else "stale")
            source_map[old_id] = source
        for item in items:
            item["id"] = "resource_" + hashlib.sha256(canonical_json(
                [query["location_scope"], catalog["version"], item["id"]]).encode()).hexdigest()[:32]
            item["source_ids"] = [source_map[identifier]["id"] for identifier in item["source_ids"]]
        search["freshness"] = ("stale" if any(source["freshness"] == "stale" for source in source_map.values())
                               else "current" if items else "unknown")
        result.update(state="available" if items else "no_match", items=items, sources=list(source_map.values()))
        result["notices"] = [notice("resource_referrals_only", "These seeded, reviewed links provide referral routes. They do not confirm a bed, food, transport, eligibility, reservation or financial saving. Confirm requirements and availability with the provider."),
                             notice("resource_bounded_catalog", "Detailed local services and program rules are not covered in this slice. Nationwide routes and a Colorado referral are bounded catalog candidates; no match does not rule out other help.")]
        if query["geography_state"] != "reported" or not query["geography"].get("state"):
            result["notices"].append(notice("resource_geography_unknown", "Only nationwide referrals can be selected without a reported state; place/ZIP is not geocoded."))
        if query["needs_state"] != "reported":
            result["notices"].append(notice("resource_needs_unknown", "Needs remain unknown; general referral routes are shown without asserting household needs."))
        if any("lost_documents" in item["need_kinds"] for item in items):
            result["notices"].append(notice("resource_issuing_jurisdiction_unknown", "Document replacement follows the document's issuing authority. Current or damaged location does not establish that jurisdiction."))
        if search["freshness"] == "stale":
            result["notices"].append(notice("resource_review_stale", "One or more referral reviews are outside the 30-day catalog review budget. Recheck the linked source before relying on contact details."))
        if search["truncated"]:
            result["notices"].append(notice("resource_results_truncated", "Only the first five matching catalog candidates are retained."))
        validate_result(result)
        return result
