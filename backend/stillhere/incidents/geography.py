"""Explicit reported geography; no geocoding or inferred location sharing."""

from ..contracts import InvalidInput, validate

# Census state/territory FIPS codes, retained as strings with leading zeroes.
STATE_FIPS = dict(pair.split(":") for pair in (
    "AL:01 AK:02 AZ:04 AR:05 CA:06 CO:08 CT:09 DE:10 DC:11 FL:12 GA:13 HI:15 "
    "ID:16 IL:17 IN:18 IA:19 KS:20 KY:21 LA:22 ME:23 MD:24 MA:25 MI:26 MN:27 "
    "MS:28 MO:29 MT:30 NE:31 NV:32 NH:33 NJ:34 NM:35 NY:36 NC:37 ND:38 OH:39 "
    "OK:40 OR:41 PA:42 RI:44 SC:45 SD:46 TN:47 TX:48 UT:49 VT:50 VA:51 WA:53 "
    "WV:54 WI:55 WY:56 AS:60 GU:66 MP:69 PR:72 VI:78"
).split())


def validate_geography(value):
    validate("IncidentGeography", value)
    if ("latitude" in value) != ("longitude" in value):
        raise InvalidInput("$.geography", "Supply both latitude and longitude.")
    if "county_fips" in value:
        if (value.get("state") not in STATE_FIPS
                or not value["county_fips"].startswith(STATE_FIPS[value["state"]])
                or value["county_fips"].endswith("000")):
            raise InvalidInput("$.geography.county_fips", "Supply a county FIPS code belonging to the reported state.")
