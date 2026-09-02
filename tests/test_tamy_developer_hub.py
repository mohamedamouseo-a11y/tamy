import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import tamy_developer_hub as hub


class TamyDeveloperHubTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.state_file = self.root / "usr" / "state.json"
        self.key_file = self.root / "usr" / ".key"
        self.patches = [
            patch.object(hub, "REPO_ROOT", self.root),
            patch.object(hub, "STATE_FILE", self.state_file),
            patch.object(hub, "KEY_FILE", self.key_file),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(
            ["git", *args],
            cwd=self.root,
            check=True,
            capture_output=True,
            text=True,
        )

    def init_repo(self):
        self.git("init", "-b", "main")
        self.git("config", "user.email", "devhub@example.invalid")
        self.git("config", "user.name", "Developer Hub Test")
        (self.root / "README.md").write_text("base\n", encoding="utf-8")
        self.git("add", "README.md")
        self.git("commit", "-m", "base")
        self.git("remote", "add", "origin", "https://github.com/mohamedamouseo-a11y/tamy.git")

    def test_origin_parser_accepts_tamy_https_and_ssh(self):
        self.assertEqual(
            hub._repo_from_origin("https://github.com/mohamedamouseo-a11y/tamy.git"),
            "mohamedamouseo-a11y/tamy",
        )
        self.assertEqual(
            hub._repo_from_origin("git@github.com:mohamedamouseo-a11y/tamy.git"),
            "mohamedamouseo-a11y/tamy",
        )

    def test_token_is_encrypted_at_rest_and_round_trips(self):
        token = "synthetic-test-token-value"
        hub._store_connection(token, {"login": "admin", "name": "Admin"})
        raw = self.state_file.read_text(encoding="utf-8")
        self.assertNotIn(token, raw)
        self.assertEqual(hub._read_token(), token)
        self.assertEqual(hub._connection_public()["user"], "admin")

    def test_sensitive_paths_are_blocked(self):
        self.assertIsNotNone(hub._blocked_path_reason(".env"))
        self.assertIsNotNone(hub._blocked_path_reason("usr/tamy_developer_hub.json"))
        self.assertIsNotNone(hub._blocked_path_reason("keys/server.pem"))
        self.assertIsNone(hub._blocked_path_reason("webui/components/example.html"))

    def test_secret_scanner_detects_github_token_pattern(self):
        token_like = "github_" + "pat_" + ("A" * 32)
        path = self.root / "sample.txt"
        path.write_text(f"token={token_like}\n", encoding="utf-8")
        findings = hub._scan_file_for_secrets("sample.txt")
        self.assertTrue(findings)
        self.assertIn("GitHub token", findings[0])

    def test_status_parser_reports_modified_and_untracked_files(self):
        self.init_repo()
        (self.root / "README.md").write_text("changed\n", encoding="utf-8")
        (self.root / "new.txt").write_text("new\n", encoding="utf-8")
        status = {item["path"]: item for item in hub._parse_status()}
        self.assertIn("README.md", status)
        self.assertIn("new.txt", status)
        self.assertTrue(status["new.txt"]["untracked"])
        self.assertTrue(status["README.md"]["unstaged"])


if __name__ == "__main__":
    unittest.main()
