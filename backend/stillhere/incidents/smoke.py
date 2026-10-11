"""Public, synthetic C03 proof. No environment files, AWS client, or household data."""

import json
from datetime import datetime, timezone
from pathlib import Path

from ..contracts import empty_case, utc_now
from .facade import IncidentFacade, build_query


def main():
    now = utc_now()
    # Deliberately public demonstration point: central Denver, Colorado.
    snapshot = empty_case("synthetic_incident_proof", "America/Denver", now)
    snapshot["facts"]["current_location"] = {"value": {"place": "Demo Denver", "latitude": 39.7392,
        "longitude": -104.9903, "state": "CO", "county_fips": "08031"},
        "state": "user_reported", "observed_at": now, "source_ids": []}
    result = IncidentFacade().collect(build_query(snapshot, {"location_scope": "current"}, now), 1)
    report = {"checked_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
              "synthetic": True, "state": result["state"], "providers": {}}
    for name, provider in result["providers"].items():
        code = provider["issue"]["code"] if provider["issue"] else None
        report["providers"][name] = {"state": provider["state"], "record_count": len(provider["records"]),
                                     "truncated": provider["truncated"], "issue_code": code}
        print(name + ":", provider["state"], "records=" + str(len(provider["records"])), "issue=" + str(code))
    path = Path("var/incident-smoke.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    print("Synthetic incident proof report:", path)
    return 0 if any(value["state"] in ("available", "no_match") for value in result["providers"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
