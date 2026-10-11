"""A strict live public-information example; no credentials, model or case writes."""

import json
import re
import time

from ..contracts import InvalidInput, utc_now
from .official import OfficialSourceFetcher, validate_fetch

SOURCE_ID = "source_usagov_lost_documents"
EVIDENCE_PHRASE = "state motor vehicle agency"


def live_guidance(result):
    """Require fresh live evidence with useful text, never a cached/failure pass."""
    validate_fetch(result)
    if result["source_id"] != SOURCE_ID or result["state"] != "available":
        raise InvalidInput("$.state", "This example requires successful live retrieval.")
    receipt = result["receipt"]
    match = re.search(r"Contact your state motor vehicle agency[^.]{0,150}\.", receipt["content"], re.IGNORECASE)
    if match is None:
        raise InvalidInput("$.receipt.content", "The expected public guidance was not in the fetched page.")
    return match.group(0)


def main():
    try:
        fetched = OfficialSourceFetcher().fetch(SOURCE_ID, utc_now(), time.monotonic() + 10)
    except TimeoutError:
        print(json.dumps({"state": "unavailable", "code": "source_timeout", "live_fetch_passed": False}, sort_keys=True))
        return 1
    try:
        excerpt = live_guidance(fetched)
    except InvalidInput:
        # Only backend-defined notice codes are printed; never raw exceptions.
        code = fetched["notices"][0]["code"] if fetched["state"] == "unavailable" and fetched["notices"] else "official_example_content_missing"
        print(json.dumps({"state": "unavailable", "code": code, "live_fetch_passed": False}, sort_keys=True))
        return 1
    receipt = fetched["receipt"]
    print(json.dumps({"state": "available", "live_fetch_passed": True, "source_id": SOURCE_ID,
                      "url": receipt["url"], "retrieved_at": receipt["retrieved_at"],
                      "content_sha256": receipt["content_sha256"], "data_mode": receipt["data_mode"],
                      "review_state": receipt["review_state"], "extracted_characters": len(receipt["content"]),
                      "truncated": receipt["truncated"], "guidance_excerpt": excerpt}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
