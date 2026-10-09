"""トークン延長の応答・ログ・保存を実ネットワークなしで検証する。"""
import contextlib
import io
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from scripts import refresh_token


OLD_TOKEN = "old-secret-test-token"
NEW_TOKEN = "new-secret-test-token"


class RefreshTokenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "new_token.txt"
        self.environ = patch.dict(os.environ, {"IG_ACCESS_TOKEN": OLD_TOKEN}, clear=True)
        self.environ.start()
        self.addCleanup(self.environ.stop)
        self.ssl_context = patch.object(refresh_token.ssl, "create_default_context", return_value=object())
        self.ssl_context.start()
        self.addCleanup(self.ssl_context.stop)

    def run_with_response(self, response):
        stream = io.BytesIO(response)
        captured = io.StringIO()
        with patch.object(refresh_token.urllib.request, "urlopen", return_value=stream) as request:
            with contextlib.redirect_stdout(captured):
                refresh_token.main(["--out", str(self.output)])
        self.assertEqual(request.call_count, 1)
        return captured.getvalue()

    def assert_failure(self, response=None, error=None):
        captured = io.StringIO()
        kwargs = {"side_effect": error} if error else {"return_value": io.BytesIO(response)}
        with patch.object(refresh_token.urllib.request, "urlopen", **kwargs):
            with contextlib.redirect_stdout(captured), self.assertRaises(SystemExit) as stopped:
                refresh_token.main(["--out", str(self.output)])
        self.assertEqual(stopped.exception.code, 1)
        self.assertFalse(self.output.exists())
        log = captured.getvalue()
        self.assertNotIn(OLD_TOKEN, log)
        self.assertNotIn(NEW_TOKEN, log)
        return log

    def test_output_is_required_before_network_access(self):
        with patch.object(refresh_token.urllib.request, "urlopen") as request:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as stopped:
                refresh_token.main([])
        self.assertEqual(stopped.exception.code, 2)
        request.assert_not_called()

    def test_success_writes_only_file_without_newline_or_token_log(self):
        log = self.run_with_response(json.dumps({"access_token": NEW_TOKEN, "expires_in": 5184000}).encode())
        self.assertEqual(self.output.read_text(encoding="utf-8"), NEW_TOKEN)
        self.assertIn("60日", log)
        self.assertNotIn(OLD_TOKEN, log)
        self.assertNotIn(NEW_TOKEN, log)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [self.output])
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)

    def test_missing_token_stops_before_network_access(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(refresh_token.urllib.request, "urlopen") as request:
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
                    refresh_token.main(["--out", str(self.output)])
        request.assert_not_called()

    def test_http_error_only_logs_numeric_identifiers(self):
        body = json.dumps({"error": {"message": NEW_TOKEN, "code": 190, "error_subcode": 463},
                           "access_token": OLD_TOKEN}).encode()
        error = urllib.error.HTTPError("https://example.invalid/?access_token=" + OLD_TOKEN,
                                       400, NEW_TOKEN, {}, io.BytesIO(body))
        log = self.assert_failure(error=error)
        self.assertIn("HTTP 400", log)
        self.assertIn("code=190", log)
        self.assertIn("error_subcode=463", log)
        self.assertNotIn("example.invalid", log)

    def test_http_error_drops_non_numeric_identifiers(self):
        body = json.dumps({"error": {"code": OLD_TOKEN, "error_subcode": True}}).encode()
        error = urllib.error.HTTPError("https://example.invalid", 400, NEW_TOKEN, {}, io.BytesIO(body))
        log = self.assert_failure(error=error)
        self.assertNotIn("code=", log)
        self.assertNotIn("True", log)

    def test_http_error_with_non_json_body_does_not_log_body(self):
        error = urllib.error.HTTPError("https://example.invalid", 500, OLD_TOKEN, {}, io.BytesIO(NEW_TOKEN.encode()))
        self.assert_failure(error=error)

    def test_transport_error_does_not_log_exception_url(self):
        self.assert_failure(error=urllib.error.URLError("https://example.invalid/?access_token=" + OLD_TOKEN))

    def test_invalid_json_does_not_log_response(self):
        self.assert_failure(response=NEW_TOKEN.encode())

    def test_non_object_response_does_not_log_response(self):
        self.assert_failure(response=json.dumps([NEW_TOKEN]).encode())

    def test_missing_or_invalid_expiry_is_failure(self):
        for expiry in (None, 0, -1, True, "5184000"):
            with self.subTest(expiry=expiry):
                self.assert_failure(response=json.dumps({"access_token": NEW_TOKEN, "expires_in": expiry}).encode())

    def test_missing_or_invalid_token_is_failure(self):
        for token in (None, "", " ", 123, "new-secret-test-token\n"):
            with self.subTest(token_type=type(token).__name__):
                self.assert_failure(response=json.dumps({"access_token": token, "expires_in": 5184000}).encode())

    def test_failed_save_does_not_log_secret_or_leave_partial_file(self):
        body = json.dumps({"access_token": NEW_TOKEN, "expires_in": 5184000}).encode()
        with patch.object(refresh_token.os, "replace", side_effect=OSError(NEW_TOKEN)):
            self.assert_failure(response=body)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
