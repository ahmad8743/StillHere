"""Local manual-review CLI. OS access to the database is its admin boundary.

Never loads environment/credential files or calls a model. Household HTTP has
no corresponding approval, queue, or publication route.
"""

import argparse
import copy
import json
from datetime import timedelta
from pathlib import Path

from ..contracts import InvalidInput, VERSION, validate
from .review import ManualReviewAuthority
from .rules import _instant


def load_public_review(path):
    path = Path(path)
    if (path.suffix.lower() != ".json" or any(part.lower().startswith(".env") or part.lower() in (".aws", "credentials", "secrets") for part in path.parts)):
        raise ValueError("Review input must be a public JSON document, never an environment or credential file.")
    if path.is_symlink():
        raise ValueError("Use a regular public review document, not a symlink.")
    resolved = path.resolve(strict=True)
    if resolved.suffix.lower() != ".json" or any(part.lower().startswith(".env") or part.lower() in (".aws", "credentials", "secrets") for part in resolved.parts):
        raise ValueError("The resolved review document must remain a public JSON file.")
    with path.open("rb") as file:
        body = file.read(65537)
    if len(body) > 65536:
        raise ValueError("Public review documents are limited to 64 KiB.")
    def pairs(entries):
        result = {}
        for key,value in entries:
            if key in result:
                raise ValueError("Duplicate review field.")
            result[key] = value
        return result
    def constant(value):
        raise ValueError("Review values must be finite JSON.")
    request = json.loads(body, object_pairs_hook=pairs, parse_constant=constant)
    validate("ManualRuleReviewRequest", request)
    return request


def draft_review(service, authority, candidate_id):
    candidate = service.read_review_candidate(authority, candidate_id)
    catalog = service.read_program_catalog()
    base = next((rule for rule in catalog["rules"] if rule["program_id"] == candidate["program_id"] and rule["version"] == candidate["base_version"]), None)
    if base is None:
        raise ValueError("The candidate base version is no longer active; review the current catalog.")
    # Draft output does not approve or persist anything. The human must inspect
    # the public excerpt and graph, choose a new version, and explicitly apply.
    now = service.clock()
    rule = copy.deepcopy(base)
    rule.update(version="EDIT_NEW_VERSION", data_mode="cached", reviewed_at=now,
                review_expires_at=(_instant(now)+timedelta(days=30)).isoformat().replace("+00:00", "Z"))
    sources = [copy.deepcopy(source) for source in catalog["sources"] if source["id"] in base["source_ids"]]
    receipt = candidate["receipt"]
    if receipt is not None:
        source = next((item for item in sources if item["id"] == receipt["source_id"]), None)
        if source is None:
            source = {"id":receipt["source_id"], "url":receipt["url"], "issuer":receipt["issuer"],
                      "jurisdiction":receipt["jurisdiction"], "updated_at":None, "supporting_sections":["EDIT_REVIEWED_SECTION"]}
            sources.append(source)
            rule["source_ids"].append(source["id"])
        source.update(retrieved_at=receipt["retrieved_at"], reviewed_at=now, expires_at=rule["review_expires_at"],
                      verification_state="official_page_reviewed", freshness="current", data_mode="cached", content_sha256=receipt["content_sha256"])
    return {"contract_version":VERSION, "event_id":"EDIT_REVIEW_EVENT_ID", "candidate_id":candidate_id,
            "expected_candidate_revision":candidate["revision"], "expected_catalog_version":catalog["version"],
            "decision":"publish", "reason":"evidence_confirmed", "publication":{"rule":rule, "sources":sources}}


def main():
    parser = argparse.ArgumentParser(description="Local manual review of public C04 candidates; no model or credential loading")
    parser.add_argument("--db", default="var/cases.sqlite3")
    parser.add_argument("--reviewer", required=True, help="Opaque local reviewer tag; authority comes from OS/database access")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("list")
    show = actions.add_parser("show"); show.add_argument("candidate_id")
    draft = actions.add_parser("draft"); draft.add_argument("candidate_id")
    apply = actions.add_parser("apply"); apply.add_argument("public_review_json")
    args = parser.parse_args()
    from ..service import CaseService, ServiceError
    try:
        authority = ManualReviewAuthority(args.reviewer)
        service = CaseService(args.db)
        if args.action == "list":
            output = service.read_review_queue(authority)
        elif args.action == "show":
            output = service.read_review_candidate(authority, args.candidate_id)
        elif args.action == "draft":
            output = draft_review(service, authority, args.candidate_id)
        else:
            request = load_public_review(args.public_review_json)
            if request["event_id"].startswith("EDIT_") or request["publication"] and request["publication"]["rule"]["version"].startswith("EDIT_"):
                raise ValueError("Review the draft and replace EDIT placeholders before applying.")
            output = service.review_rule_candidate(authority, request)
        print(json.dumps(output, indent=2))
        return 0
    except ServiceError as error:
        print("Manual review incomplete:", error.issue["code"])
    except (ValueError, OSError):
        print("Manual review incomplete: invalid_public_review")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
