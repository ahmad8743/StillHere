"""User-run read-only Bedrock access checks; no subscriptions or inference calls."""

from .diagnostics import failure, record, safe_access_status


def check_access(config, diagnostics, *, expected_account_id=None, session=None):
    """Use the provider's credential chain; retain only fixed status labels.

    Tests inject a fake session. Only the user-run CLI creates a real SDK session.
    Account IDs, ARNs, model IDs, form data and AWS messages are never emitted.
    """
    status = {"account_match": "NOT_CHECKED", "profile": "NOT_APPLICABLE",
              "use_case": "UNKNOWN" if "anthropic." in config.model_id else "NOT_APPLICABLE"}
    record(diagnostics, "access_check_started")

    def attempt(event, operation):
        record(diagnostics, event)
        try:
            return operation()
        except Exception as error:
            failure(diagnostics, error)
            return None

    client_options = {"region_name": config.region}
    if session is None:
        try:
            import boto3
            from botocore.config import Config
            session = boto3.Session()
            client_options["config"] = Config(connect_timeout=5, read_timeout=min(15, config.timeout_seconds),
                                               retries={"total_max_attempts": 2, "mode": "standard"})
        except Exception as error:
            failure(diagnostics, error)
            status = safe_access_status({})
            record(diagnostics, "access_check_complete", access_status=status)
            return status

    if expected_account_id is not None:
        identity = attempt("access_identity_started",
                           lambda: session.client("sts", **client_options).get_caller_identity())
        actual = identity.get("Account") if isinstance(identity, dict) else None
        status["account_match"] = "MATCH" if actual == expected_account_id else "MISMATCH" if isinstance(actual, str) and actual else "UNKNOWN"

    bedrock = attempt("access_profile_started", lambda: session.client("bedrock", **client_options))
    if bedrock is not None:
        model_id = config.model_id
        is_profile = model_id.startswith(("us.", "eu.", "apac.", "global.", "au.", "jp.", "in.")) or "inference-profile/" in model_id
        if is_profile:
            status["profile"] = "UNKNOWN"
            profile = attempt("access_profile_started",
                              lambda: bedrock.get_inference_profile(inferenceProfileIdentifier=config.model_id))
            model_id = None
            if isinstance(profile, dict):
                status["profile"] = profile.get("status")
                # Routing regions may differ, but a system profile identifies one
                # foundation model. Never guess or send the profile ID to availability.
                models = profile.get("models", [])
                models = models if isinstance(models, list) else []
                model_ids = {item["modelArn"].split(":foundation-model/", 1)[1]
                             for item in models if isinstance(item, dict)
                             and isinstance(item.get("modelArn"), str) and ":foundation-model/" in item["modelArn"]}
                if len(model_ids) == 1:
                    model_id = model_ids.pop()
        elif ":foundation-model/" in model_id:
            model_id = model_id.split(":foundation-model/", 1)[1]

        if model_id and model_id.startswith("anthropic."):
            status["use_case"] = "UNKNOWN"
            form = attempt("access_form_started", bedrock.get_use_case_for_model_access)
            if isinstance(form, dict):
                data = form.get("formData")
                if isinstance(data, (str, bytes, bytearray)):
                    status["use_case"] = "SUBMITTED" if data else "NOT_VISIBLE"
            elif diagnostics.provider_failure and diagnostics.provider_failure.get("code") == "ResourceNotFoundException":
                status["use_case"] = "NOT_VISIBLE"

        if model_id:
            availability = attempt("access_availability_started",
                                   lambda: bedrock.get_foundation_model_availability(modelId=model_id))
            if isinstance(availability, dict):
                agreement = availability.get("agreementAvailability", {})
                status.update({"agreement": agreement.get("status") if isinstance(agreement, dict) else None,
                               "authorization": availability.get("authorizationStatus"),
                               "entitlement": availability.get("entitlementAvailability"),
                               "region": availability.get("regionAvailability")})

    status = safe_access_status(status)
    record(diagnostics, "access_check_complete", access_status=status)
    return status


def access_ready(status):
    # These are control-plane checks, not proof that a live turn will succeed.
    return (status["account_match"] in ("MATCH", "NOT_CHECKED")
            and status["profile"] in ("ACTIVE", "NOT_APPLICABLE")
            and status["use_case"] in ("SUBMITTED", "NOT_APPLICABLE")
            and status["agreement"] == "AVAILABLE" and status["authorization"] == "AUTHORIZED"
            and status["entitlement"] == "AVAILABLE" and status["region"] == "AVAILABLE")
