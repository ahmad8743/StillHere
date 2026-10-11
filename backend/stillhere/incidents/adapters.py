"""Normalize official provider records; unknown data never becomes a negative claim."""

import hashlib
import math
from datetime import datetime, timezone
from urllib.parse import urlencode, urlsplit

from ..contracts import canonical_json
from .geography import STATE_FIPS
from .transport import SourceFailure

MAX_RECORDS = 5
ENDPOINTS = {"nws": "https://api.weather.gov/alerts/active",
             "usgs": "https://earthquake.usgs.gov/fdsnws/event/1/query",
             "openfema": "https://www.fema.gov/api/open/v2/DisasterDeclarationsSummaries"}
REFERRALS = {"nws": "https://www.weather.gov/alerts",
             "usgs": "https://earthquake.usgs.gov/earthquakes/map/",
             "openfema": "https://www.fema.gov/disaster/declarations"}
ISSUERS = {"nws": "National Weather Service", "usgs": "US Geological Survey", "openfema": "FEMA"}


def instant(value, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise ValueError()
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError()
    return parsed.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def epoch_ms(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError()
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def text(value, limit=512, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError()
    return value[:limit]


def official_link(value, provider):
    if not isinstance(value, str) or len(value) > 1024:
        raise ValueError()
    parsed = urlsplit(value)
    allowed = {"nws": {"api.weather.gov", "www.weather.gov"},
               "usgs": {"earthquake.usgs.gov"}, "openfema": {"www.fema.gov"}}[provider]
    if (parsed.scheme != "https" or parsed.hostname not in allowed or parsed.port not in (None, 443)
            or parsed.username or parsed.password):
        raise ValueError()
    return value


def request_url(provider, query):
    geo = query["geography"]
    point = "latitude" in geo and "longitude" in geo
    if provider == "nws":
        if point:
            params = {"point": f"{geo['latitude']},{geo['longitude']}"}
        elif "state" in geo:
            params = {"area": geo["state"]}
        else:
            return None
        # The active endpoint has no limit parameter. Bound bytes in transport,
        # then retain five records and expose truncation rather than requesting an invalid filter.
        params.update(status="actual", message_type="alert,update")
    elif provider == "usgs":
        if not point:
            return None
        params = {"format": "geojson", "latitude": geo["latitude"], "longitude": geo["longitude"],
                  "maxradiuskm": 100, "minmagnitude": 2.5, "eventtype": "earthquake",
                  "starttime": query["start_at"], "endtime": query["end_at"],
                  "limit": MAX_RECORDS + 1, "orderby": "time", "nodata": 204}
    else:
        if "state" not in geo:
            return None
        filters = [f"state eq '{geo['state']}'", f"declarationDate ge '{query['start_at']}'",
                   f"declarationDate le '{query['end_at']}'"]
        if "county_fips" in geo:
            filters.append(f"(fipsCountyCode eq '{geo['county_fips'][2:]}' or fipsCountyCode eq '000')")
        params = {"$filter": " and ".join(filters), "$top": MAX_RECORDS + 1,
                  "$orderby": "declarationDate desc,disasterNumber desc"}
    return ENDPOINTS[provider] + "?" + urlencode(params)


def record_base(provider, key, query, title, url, effective, updated, expires, area, details, summary=None, instructions=None):
    if not isinstance(key, str) or not key or len(key) > 512:
        raise ValueError()
    identity = hashlib.sha256(canonical_json([provider, key, query["location_scope"]]).encode()).hexdigest()[:32]
    return {"id": "incident_" + identity, "provider_record_id": key,
            "kind": {"nws": "weather_alert", "usgs": "earthquake", "openfema": "disaster_declaration"}[provider],
            "title": text(title, 256, required=True), "url": official_link(url, provider),
            "summary": text(summary), "instructions": text(instructions),
            "text_truncated": any(isinstance(value, str) and len(value) > limit for value, limit in ((title, 256), (summary, 512), (instructions, 512))),
            "effective_at": effective, "source_updated_at": updated, "expires_at": expires,
            "geographic_scope": area, "details": details}


def features(payload):
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection" or not isinstance(payload.get("features"), list):
        raise ValueError()
    return payload["features"]


def nws_records(payload, query):
    rows = features(payload)
    records = []
    for row in rows[:MAX_RECORDS + 1]:
        if not isinstance(row, dict) or not isinstance(row.get("properties"), dict):
            raise ValueError()
        props = row["properties"]
        if props.get("status") not in ("Actual", "Test", "Exercise", "System", "Draft"):
            raise ValueError()
        if props["status"] != "Actual" or props.get("messageType") == "Cancel":
            continue
        if props.get("messageType") not in ("Alert", "Update"):
            raise ValueError()
        expires = instant(props.get("expires"), True)
        ends = instant(props.get("ends"))
        # Expiry/end are authoritative bounds even if the feed erroneously includes an old alert.
        if min(value for value in (expires, ends) if value) <= query["end_at"]:
            continue
        geo = query["geography"]
        area = {"match": "point_query" if "latitude" in geo else "state_query",
                "description": text(props.get("areaDesc"), 256, True)}
        records.append(record_base("nws", props.get("id"), query, props.get("headline") or props.get("event"),
                                   row.get("id") or props.get("@id"), instant(props.get("effective"), True),
                                   instant(props.get("sent"), True), min(v for v in (expires, ends) if v), area,
                                   {"event": text(props.get("event"), 128, True),
                                    "severity": text(props.get("severity"), 32), "certainty": text(props.get("certainty"), 32),
                                    "urgency": text(props.get("urgency"), 32)},
                                   props.get("description"), props.get("instruction")))
    return records, len(rows) > MAX_RECORDS or bool(payload.get("pagination", {}).get("next"))


def distance_km(lat1, lon1, lat2, lon2):
    first, second = math.radians(lat1), math.radians(lat2)
    a = math.sin((second - first) / 2) ** 2 + math.cos(first) * math.cos(second) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(a)))


def usgs_records(payload, query):
    rows = features(payload)
    records = []
    for row in rows[:MAX_RECORDS + 1]:
        props, geometry = row["properties"], row["geometry"]
        if not isinstance(props, dict) or not isinstance(geometry, dict) or geometry.get("type") != "Point":
            raise ValueError()
        coords = geometry.get("coordinates")
        if not isinstance(coords, list) or len(coords) < 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in coords[:3]):
            raise ValueError()
        longitude, latitude, depth = coords[:3]
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            raise ValueError()
        effective, updated = epoch_ms(props.get("time")), epoch_ms(props.get("updated"))
        magnitude = props.get("mag")
        if magnitude is not None and (type(magnitude) not in (int, float) or not math.isfinite(magnitude)):
            raise ValueError()
        if (props.get("type") != "earthquake" or not query["start_at"] <= effective <= query["end_at"]
                or distance_km(query["geography"]["latitude"], query["geography"]["longitude"], latitude, longitude) > 100):
            continue
        if magnitude is not None and magnitude < 2.5:
            continue
        records.append(record_base("usgs", row.get("id"), query, props.get("title") or props.get("place"),
                                   props.get("url"), effective, updated, None,
                                   {"match": "within_radius", "description": text(props.get("place"), 256, True),
                                    "latitude": latitude, "longitude": longitude, "radius_km": 100},
                                   {"magnitude": magnitude, "depth_km": depth, "review_status": text(props.get("status"), 32)}))
    return records, len(rows) > MAX_RECORDS


def fips(value, width):
    if type(value) is int:
        value = str(value)
    if not isinstance(value, str) or not value.isascii() or not value.isdigit() or len(value) > width:
        raise ValueError()
    return value.zfill(width)


def fema_records(payload, query):
    if not isinstance(payload, dict) or not isinstance(payload.get("DisasterDeclarationsSummaries"), list):
        raise ValueError()
    rows, records = payload["DisasterDeclarationsSummaries"], []
    for row in rows[:MAX_RECORDS + 1]:
        state, county = row["state"], fips(row["fipsCountyCode"], 3)
        state_fips = fips(row["fipsStateCode"], 2)
        if state not in STATE_FIPS or STATE_FIPS[state] != state_fips:
            raise ValueError()
        declared = instant(row.get("declarationDate"), True)
        begin, end = instant(row.get("incidentBeginDate"), True), instant(row.get("incidentEndDate"))
        if end is not None and end < begin:
            raise ValueError()
        geo = query["geography"]
        if state != geo["state"] or not query["start_at"] <= declared <= query["end_at"] or begin > query["end_at"]:
            continue
        if geo.get("county_fips") and county != "000" and geo["county_fips"] != state_fips + county:
            continue
        flags = {}
        for source, target in (("ihProgramDeclared", "individuals_households"), ("iaProgramDeclared", "individual_assistance"),
                               ("paProgramDeclared", "public_assistance"), ("hmProgramDeclared", "hazard_mitigation")):
            value = row.get(source)
            if value is not None and type(value) is not bool:
                raise ValueError()
            flags[target] = value
        number = row.get("disasterNumber")
        if type(number) is not int or number <= 0:
            raise ValueError()
        details = {"disaster_number": number, "declaration_type": text(row.get("declarationType"), 16, True),
                   "incident_type": text(row.get("incidentType"), 128, True), "declaration_date": declared,
                   "incident_begin_at": begin, "incident_end_at": end, "designated_programs": flags,
                   "household_eligibility": "unknown"}
        records.append(record_base("openfema", row.get("id"), query, row.get("declarationTitle"),
                                   f"https://www.fema.gov/disaster/{number}", begin, instant(row.get("lastRefresh")), None,
                                   {"match": "county_match" if county != "000" and geo.get("county_fips") else "state_query",
                                    "description": text(row.get("designatedArea"), 256, True), "state": state,
                                    "county_fips": state_fips + county if county != "000" else None}, details))
    return records, len(rows) > MAX_RECORDS


NORMALIZERS = {"nws": nws_records, "usgs": usgs_records, "openfema": fema_records}


def normalize(provider, payload, query):
    try:
        records, truncated = NORMALIZERS[provider](payload, query)
        # Keep stable identities and only the bounded latest results.
        unique = {record["id"]: record for record in records}
        return sorted(unique.values(), key=lambda item: item["source_updated_at"] or item["effective_at"], reverse=True)[:MAX_RECORDS], truncated
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
        raise SourceFailure("source_invalid_response") from None
