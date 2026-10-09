"""Read-only automation checks: no real credentials, API calls, or publication."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


config = load_script("check_config")
post = load_script("post_instagram")

SECRET_VALUES = {
    "IG_USER_ID": "test-user-id-never-log",
    "IG_ACCESS_TOKEN": "test-ig-token-never-log",
    "GH_PAT": "test-pat-never-log",
    "DIGEST_TO": "test-recipient-never-log@example.invalid",
    "SMTP_USER": "test-smtp-user-never-log@example.invalid",
    "SMTP_PASS": "test-smtp-password-never-log",
}


def invoke_main(module, argv):
    """Support both return-code main functions and explicit SystemExit."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with patch("sys.argv", [f"{module.__name__}.py", *argv]), \
            contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            result = module.main()
            code = result if isinstance(result, int) else 0
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 1
    return code, stdout.getvalue() + stderr.getvalue()


class ConfigInspectionTests(unittest.TestCase):
    def test_post_empty_reports_both_required_names(self):
        result = config.inspect_config("post", {})
        self.assertFalse(result["ready"])
        self.assertEqual(result["missing"], ["IG_USER_ID", "IG_ACCESS_TOKEN"])

    def test_refresh_empty_reports_both_required_names(self):
        result = config.inspect_config("refresh", {})
        self.assertFalse(result["ready"])
        self.assertEqual(result["missing"], ["IG_ACCESS_TOKEN", "GH_PAT"])

    def test_whitespace_counts_as_unset(self):
        result = config.inspect_config("post", {name: " \n\t" for name in SECRET_VALUES})
        self.assertFalse(result["ready"])
        self.assertFalse(result["mail_ready"])
        self.assertEqual(len(result["missing"]), 2)
        self.assertEqual(len(result["mail_missing"]), 3)

    def test_post_with_only_user_id_identifies_token(self):
        result = config.inspect_config("post", {"IG_USER_ID": "test-id"})
        self.assertEqual(result["missing"], ["IG_ACCESS_TOKEN"])

    def test_post_with_only_token_identifies_user_id(self):
        result = config.inspect_config("post", {"IG_ACCESS_TOKEN": "test-token"})
        self.assertEqual(result["missing"], ["IG_USER_ID"])

    def test_refresh_with_only_token_identifies_pat(self):
        result = config.inspect_config("refresh", {"IG_ACCESS_TOKEN": "test-token"})
        self.assertEqual(result["missing"], ["GH_PAT"])

    def test_refresh_with_only_pat_identifies_token(self):
        result = config.inspect_config("refresh", {"GH_PAT": "test-pat"})
        self.assertEqual(result["missing"], ["IG_ACCESS_TOKEN"])

    def test_complete_settings_ready_for_both_purposes(self):
        for purpose in ("post", "refresh"):
            with self.subTest(purpose=purpose):
                result = config.inspect_config(purpose, SECRET_VALUES)
                self.assertTrue(result["ready"])
                self.assertTrue(result["mail_ready"])
                self.assertEqual(result["missing"], [])
                self.assertEqual(result["mail_missing"], [])

    def test_missing_mail_does_not_hide_primary_configuration(self):
        result = config.inspect_config("post", {
            "IG_USER_ID": "test-id", "IG_ACCESS_TOKEN": "test-token",
        })
        self.assertTrue(result["ready"])
        self.assertFalse(result["mail_ready"])
        self.assertEqual(result["mail_missing"], ["DIGEST_TO", "SMTP_USER", "SMTP_PASS"])

    def test_partial_mail_settings_identify_only_missing_name(self):
        env = dict(SECRET_VALUES)
        del env["SMTP_PASS"]
        result = config.inspect_config("post", env)
        self.assertTrue(result["ready"])
        self.assertEqual(result["mail_missing"], ["SMTP_PASS"])

    def test_post_dry_run_needs_no_credentials(self):
        result = config.inspect_config("post", {}, dry_run=True)
        self.assertTrue(result["ready"])
        self.assertEqual(result["missing"], [])

    def test_refresh_cannot_bypass_settings_with_dry_run(self):
        result = config.inspect_config("refresh", {}, dry_run=True)
        self.assertFalse(result["ready"])

    def test_diagnostics_never_contain_secret_values(self):
        for purpose in ("post", "refresh"):
            with self.subTest(purpose=purpose):
                text = json.dumps(config.inspect_config(purpose, SECRET_VALUES))
                for value in SECRET_VALUES.values():
                    self.assertNotIn(value, text)


class ConfigCliTests(unittest.TestCase):
    def run_config(self, env, argv):
        with tempfile.TemporaryDirectory(prefix=".test-automation-", dir=ROOT) as temp_dir:
            output = Path(temp_dir) / "outputs.txt"
            summary = Path(temp_dir) / "summary.md"
            process_env = dict(env, GITHUB_OUTPUT=str(output), GITHUB_STEP_SUMMARY=str(summary))
            with patch.dict(os.environ, process_env, clear=True), \
                    patch("urllib.request.urlopen", side_effect=AssertionError("Network is forbidden")):
                code, log = invoke_main(config, argv)
            contents = log
            if output.exists():
                contents += output.read_text(encoding="utf-8")
            if summary.exists():
                contents += summary.read_text(encoding="utf-8")
            return code, contents, output.read_text(encoding="utf-8") if output.exists() else ""

    def test_missing_required_settings_exit_nonzero_and_report_names(self):
        code, text, output = self.run_config({}, ["--purpose", "post"])
        self.assertEqual(code, 1)
        self.assertIn("IG_USER_ID", text)
        self.assertIn("IG_ACCESS_TOKEN", text)
        self.assertIn("ready=false", output)

    def test_complete_settings_emit_only_fixed_outputs_and_no_values(self):
        code, text, output = self.run_config(SECRET_VALUES, ["--purpose", "refresh"])
        self.assertEqual(code, 0)
        self.assertIn("ready=true", output)
        self.assertIn("mail_ready=true", output)
        keys = {line.partition("=")[0] for line in output.splitlines() if "=" in line}
        self.assertEqual(keys, {"ready", "missing", "reason", "mail_ready", "mail_missing"})
        for value in SECRET_VALUES.values():
            self.assertNotIn(value, text)

    def test_dry_run_succeeds_without_ig_or_smtp_settings(self):
        code, _, output = self.run_config({}, ["--purpose", "post", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("ready=true", output)
        self.assertIn("mail_ready=false", output)


class PostSelectionTests(unittest.TestCase):
    @staticmethod
    def entry(number="01", posted=False, when="2000-01-01 08:00"):
        return {"番号": number, "タイトル": "test", "投稿済み": posted, "予定時刻": when}

    def test_forced_posted_entry_is_rejected(self):
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as error:
            post.pick({"予定": [self.entry(posted=True)]}, "01")
        self.assertEqual(error.exception.code, 1)

    def test_dry_run_can_inspect_forced_posted_entry(self):
        entry = self.entry(posted=True)
        self.assertIs(post.pick({"予定": [entry]}, "01", allow_posted=True), entry)

    def test_forced_unposted_entry_is_selected(self):
        entry = self.entry()
        self.assertIs(post.pick({"予定": [entry]}, "01"), entry)

    def test_automatic_selection_skips_posted_and_returns_first_due_entry(self):
        first = self.entry(posted=True)
        second = self.entry(number="02")
        third = self.entry(number="03")
        self.assertIs(post.pick({"予定": [first, second, third]}, None), second)

    def test_future_schedule_returns_no_target(self):
        self.assertIsNone(post.pick({"予定": [self.entry(when="2999-01-01 08:00")]}, None))

    def test_unknown_forced_number_is_rejected(self):
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit):
            post.pick({"予定": [self.entry()]}, "99")


class PostDryRunTests(unittest.TestCase):
    def run_post(self, argv, posted=False, image_count=1):
        with tempfile.TemporaryDirectory(prefix=".test-automation-", dir=ROOT) as temp_dir:
            root = Path(temp_dir)
            schedule_path = root / "schedule.json"
            schedule_path.write_text(json.dumps({"予定": [PostSelectionTests.entry(posted=posted)]}),
                                     encoding="utf-8")
            posts_path = root / "posts"
            image_dir = posts_path / "01"
            image_dir.mkdir(parents=True)
            for index in range(image_count):
                (image_dir / f"{index + 1:02}.png").write_bytes(b"test fixture; no upload")
            captions = posts_path / "captions"
            captions.mkdir()
            (captions / "01.txt").write_text("Test caption\nNo real publication.", encoding="utf-8")
            before = schedule_path.read_bytes()
            env = dict(SECRET_VALUES, GITHUB_REPOSITORY="example/happa-no-uragawa")
            with patch.dict(os.environ, env, clear=True), \
                    patch.object(post, "SCHEDULE", str(schedule_path)), \
                    patch.object(post, "POSTS", str(posts_path)), \
                    patch.object(post, "IG", side_effect=AssertionError("IG creation is forbidden")) as ig_mock, \
                    patch.object(post, "request", side_effect=AssertionError("API is forbidden")) as api_mock, \
                    patch("urllib.request.urlopen", side_effect=AssertionError("Network is forbidden")):
                code, log = invoke_main(post, argv)
            self.assertEqual(before, schedule_path.read_bytes(), "schedule.json must remain unchanged")
            ig_mock.assert_not_called()
            api_mock.assert_not_called()
            for value in SECRET_VALUES.values():
                self.assertNotIn(value, log)
            return code, log

    def test_dry_run_does_not_publish_or_modify_schedule(self):
        code, log = self.run_post(["--no", "01", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("--dry-run", log)

    def test_dry_run_can_read_already_posted_target_without_publishing(self):
        code, _ = self.run_post(["--no", "01", "--dry-run"], posted=True)
        self.assertEqual(code, 0)

    def test_real_mode_rejects_already_posted_target_before_api(self):
        code, _ = self.run_post(["--no", "01"], posted=True)
        self.assertEqual(code, 1)

    def test_dry_run_rejects_empty_images_without_schedule_change(self):
        code, _ = self.run_post(["--no", "01", "--dry-run"], image_count=0)
        self.assertEqual(code, 1)

    def test_dry_run_rejects_more_than_ten_images(self):
        code, _ = self.run_post(["--no", "01", "--dry-run"], image_count=11)
        self.assertEqual(code, 1)

    def test_invalid_cli_argument_stops_before_api(self):
        code, _ = self.run_post(["--no", "01", "--unexpected-option"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
