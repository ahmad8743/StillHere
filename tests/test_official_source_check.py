"""Public-source diagnosis reports useful categories without raw error/content."""

import io
import json
import socket
import ssl
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from backend.stillhere.knowledge.check_source import check_source, main
from tests.test_knowledge import Opener, Response, SOURCE


class OfficialSourceCheckTests(unittest.TestCase):
    def test_http_rejection_reports_status_without_response_message_or_url(self):
        error = HTTPError("https://private.invalid/?token=private_marker", 403, "private_marker", {}, None)
        result = check_source(SOURCE, delegate=Opener(error=error))
        self.assertEqual(result["state"], "unavailable")
        self.assertEqual(result["code"], "source_http_error")
        self.assertEqual(result["http_status"], 403)
        self.assertEqual(result["reason"], "http_error")
        self.assertNotIn("private_marker", json.dumps(result))

    def test_network_causes_are_fixed_categories_without_exception_messages(self):
        for cause, reason in ((socket.gaierror(-2, "private_marker"), "dns_error"),
                              (ssl.SSLError("private_marker"), "tls_error"),
                              (TimeoutError("private_marker"), "timeout"),
                              (ConnectionRefusedError("private_marker"), "connection_refused"),
                              (ConnectionResetError("private_marker"), "connection_reset"),
                              ("private_marker", "network_error")):
            with self.subTest(reason=reason):
                result = check_source(SOURCE, delegate=Opener(error=URLError(cause)))
                self.assertEqual(result["state"], "unavailable")
                self.assertEqual(result["reason"], reason)
                self.assertNotIn("private_marker", json.dumps(result))

    def test_success_reports_only_status_count_and_truncation(self):
        result = check_source(SOURCE, delegate=Opener(Response(b"<main>private_marker</main>")))
        self.assertEqual(result["state"], "available")
        self.assertEqual(result["http_status"], 200)
        self.assertEqual(result["extracted_characters"], len("private_marker"))
        self.assertNotIn("private_marker", json.dumps(result))

    def test_invalid_body_is_distinct_from_successful_http_request(self):
        result = check_source(SOURCE, delegate=Opener(Response(b"private_marker", "application/json")))
        self.assertEqual(result["state"], "unavailable")
        self.assertEqual(result["http_status"], 200)
        self.assertEqual(result["code"], "source_invalid_response")
        self.assertNotIn("private_marker", json.dumps(result))

    def test_unknown_source_and_invalid_limits_never_open_network(self):
        opener = Opener()
        for source, timeout in (("private_marker", 10), (SOURCE, 0), (SOURCE, 31), (SOURCE, True)):
            with self.subTest(source=source, timeout=timeout), self.assertRaises(ValueError):
                check_source(source, timeout, opener)
        self.assertEqual(opener.requests, [])

    def test_cli_exit_status_matches_fetch_result_without_model_configuration(self):
        for state, code in (("available", 0), ("unavailable", 1)):
            output = io.StringIO()
            with patch("sys.argv", ["check_source"]), \
                 patch("backend.stillhere.knowledge.check_source.check_source", return_value={"state": state}) as check, \
                 redirect_stdout(output):
                self.assertEqual(main(), code)
            self.assertEqual(json.loads(output.getvalue()), {"state": state})
            check.assert_called_once_with(SOURCE, 10)
