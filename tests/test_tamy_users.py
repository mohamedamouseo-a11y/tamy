import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from helpers import tamy_users


class TamyUsersTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "users.json"
        self.path_patch = patch.object(tamy_users, "_USERS_FILE", self.path)
        self.path_patch.start()

    def tearDown(self):
        self.path_patch.stop()
        self.tmp.cleanup()

    def test_first_user_is_superadmin_and_authenticates(self):
        user = tamy_users.create_user("admin", "password123", role="user")
        self.assertEqual(user["role"], "superadmin")
        self.assertIsNotNone(tamy_users.authenticate("admin", "password123"))
        self.assertNotIn("password_hash", tamy_users.list_users()[0])

    def test_wrong_password_fails(self):
        tamy_users.create_user("admin", "password123")
        self.assertIsNone(tamy_users.authenticate("admin", "wrong-password"))

    def test_last_superadmin_cannot_be_removed(self):
        tamy_users.create_user("admin", "password123")
        with self.assertRaises(ValueError): tamy_users.update_user("admin", role="user")
        with self.assertRaises(ValueError): tamy_users.update_user("admin", active=False)
        with self.assertRaises(ValueError): tamy_users.delete_user("admin")

    def test_second_admin_allows_role_change(self):
        tamy_users.create_user("admin", "password123")
        tamy_users.create_user("admin2", "password456", role="superadmin")
        self.assertEqual(tamy_users.update_user("admin", role="user")["role"], "user")

    def test_password_change_revokes_old_password(self):
        tamy_users.create_user("admin", "password123")
        tamy_users.update_user("admin", password="new-password123")
        self.assertIsNone(tamy_users.authenticate("admin", "password123"))
        self.assertIsNotNone(tamy_users.authenticate("admin", "new-password123"))


if __name__ == "__main__":
    unittest.main()
