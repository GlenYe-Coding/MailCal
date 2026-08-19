import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from config_store import _env_overrides, validate_config


class ConfigStoreTest(unittest.TestCase):
    def test_validate_missing_email(self):
        errors = validate_config({"email": "", "auth_code": "x", "imap_host": "imap.qq.com", "imap_port": 993})
        self.assertIn("邮箱不能为空", errors)

    def test_validate_missing_auth(self):
        errors = validate_config({"email": "a@qq.com", "auth_code": "", "imap_host": "imap.qq.com", "imap_port": 993})
        self.assertIn("授权码不能为空", errors)

    def test_validate_invalid_port(self):
        errors = validate_config({"email": "a@qq.com", "auth_code": "x", "imap_host": "imap.qq.com", "imap_port": 99999})
        self.assertIn("IMAP 端口必须在 1-65535 之间", errors)

    def test_env_override_mapping(self):
        os.environ["EMAIL_CALENDAR_EMAIL"] = "env@qq.com"
        os.environ["EMAIL_CALENDAR_IMAP_PORT"] = "143"
        try:
            overrides = _env_overrides()
            self.assertEqual(overrides["email"], "env@qq.com")
            self.assertEqual(overrides["imap_port"], 143)
        finally:
            os.environ.pop("EMAIL_CALENDAR_EMAIL", None)
            os.environ.pop("EMAIL_CALENDAR_IMAP_PORT", None)


if __name__ == "__main__":
    unittest.main()
