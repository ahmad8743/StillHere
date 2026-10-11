"""One bounded facade for official hazard/event/declaration context."""

import copy
import hashlib
import time
from datetime import datetime, timedelta

from ..contracts import InvalidInput, VERSION, canonical_json, utc_now, validate
from .adapters import ENDPOINTS, ISSUERS, MAX_RECORDS, REFERRALS, instant, normalize, request_url
from .geography import validate_geography
from .transport import PublicJSONTransport, SourceFailure


def query_identity(query):
    return {key: copy.deepcopy(query[key]) for key in ("location_scope", "geography", "geography_state", "crisis_type", "lookback_days")}


def build_query(snapshot, arguments, now):
    validate("IncidentToolArguments", arguments)
    scope = arguments["location_scope"]
    fact = snapshot["facts"].get(scope + "_location", {})
    value = fact.get("value")
    geography, state = {}, "unknown"
    if fact.get("state") in ("user_reported", "source_supported") and isinstance(value, dict):
        keys = ("place", "postal_code", "latitude", "longitude", "state", "county_fips")
        geography = {key: copy.deepcopy(value[key]) for key in keys if key in value}
        try:
            validate_geography(geography)
            state = "reported" if geography else "unknown"
        except InvalidInput:
            geography, state = {}, "invalid"
    crisis_fact = snapshot["facts"].get("crisis_type", {})
    crisis = crisis_fact.get("value") if crisis_fact.get("state") in ("user_reported", "source_supported") else None
    if crisis not in ("flood", "storm_hurricane", "wildfire", "earthquake", "other"):
        crisis = "unknown"
    end = instant(now, True)
    days = arguments.get("lookback_days", 30)
    start = (datetime.fromisoformat(end.replace("Z", "+00:00")) - timedelta(days=days)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    query = {"location_scope": scope, "geography": geography, "geography_state": state,
             "crisis_type": crisis, "lookback_days": days, "start_at": start, "end_at": end}
    validate("IncidentQuery", query)
    return query


def notice(code, message):
    return {"code": code, "message": message, "retryable": False}


class IncidentFacade:
    def __init__(self, transport=None, clock=utc_now):
        self.transport = transport or PublicJSONTransport()
        self.clock = clock

    def collect(self, query, input_case_version, deadline=None):
        validate("IncidentQuery", query)
        validate_geography(query["geography"])
        deadline = min(deadline if deadline is not None else float("inf"), time.monotonic() + 20)
        providers = {}
        for provider in ENDPOINTS:
            records, truncated, issue = [], False, None
            url = request_url(provider, query)
            state = "unknown"
            if url is None:
                issue = notice("incident_geography_unknown", "Reported geography is insufficient for this provider; no lookup was attempted.")
            else:
                try:
                    if time.monotonic() >= deadline:
                        raise SourceFailure("source_timeout")
                    payload = self.transport.get_json(url, deadline)
                    if time.monotonic() >= deadline:
                        raise SourceFailure("source_timeout")
                    records, truncated = normalize(provider, payload, query)
                    state = "available" if records else "unknown" if truncated else "no_match"
                except SourceFailure as error:
                    state = "unavailable"
                    issue = notice(error.code, "The official source could not provide validated context. Use its official referral; absence is not established.")
            retrieved = instant(self.clock(), True)
            fresh_until = (datetime.fromisoformat(retrieved.replace("Z", "+00:00"))
                           + timedelta(seconds=3600 if provider == "openfema" else 300)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            expiries = [record["expires_at"] for record in records if record["expires_at"]]
            if expiries:
                fresh_until = min(fresh_until, *expiries)
            if state in ("unknown", "unavailable"):
                fresh_until = retrieved
            source_id = "source_incident_" + hashlib.sha256(canonical_json([provider, query_identity(query)]).encode()).hexdigest()[:32]
            source = {"id": source_id, "provider": provider, "url": url or ENDPOINTS[provider],
                      "issuer": ISSUERS[provider], "location_scope": query["location_scope"],
                      "geography": copy.deepcopy(query["geography"]), "retrieved_at": retrieved,
                      "source_updated_at": max((record["source_updated_at"] for record in records if record["source_updated_at"]), default=None),
                      "fresh_until": fresh_until, "verification_state": "official_api" if state in ("available", "no_match") else "unverified",
                      "availability_state": state, "referral_url": REFERRALS[provider]}
            for record in records:
                record["source_id"] = source_id
            providers[provider] = {"state": state, "source": source, "records": records,
                                   "truncated": truncated, "issue": issue}
        states = [value["state"] for value in providers.values()]
        complete = all(state in ("available", "no_match") for state in states)
        if complete:
            state = "available" if "available" in states else "no_match"
        elif any(state in ("available", "no_match") for state in states):
            state = "partial"
        else:
            state = "unavailable" if "unavailable" in states else "unknown"
        notices = [notice("incident_context_only", "Alerts, earthquake events and declaration/program flags do not establish household eligibility, live capacity or agency approval."),
                   notice("incident_bounded_search", "NWS covers active alerts; USGS covers magnitude 2.5+ earthquakes within 100 km in the stated time window; FEMA covers declarations dated in that window. No match does not rule out a disaster or other support.")]
        if not complete:
            notices.append(notice("incident_partial_coverage", "One or more sources are unavailable or need more reported geography; inspect each provider state."))
        if any(value["truncated"] for value in providers.values()):
            notices.append(notice("incident_results_truncated", f"Results are limited to {MAX_RECORDS} records per provider and do not establish exhaustive coverage."))
        result = {"contract_version": VERSION, "input_case_version": input_case_version, "query": copy.deepcopy(query),
                  "retrieved_at": instant(self.clock(), True), "state": state, "providers": providers, "notices": notices}
        validate("IncidentContext", result)
        return result
