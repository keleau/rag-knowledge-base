from __future__ import annotations

import unittest

import pii


class PiiTests(unittest.TestCase):
    def test_mask_phone(self) -> None:
        masked = pii.mask("我的手机号是 13812345678，请联系我")
        self.assertNotIn("13812345678", masked)
        self.assertIn("138****5678", masked)

    def test_mask_email(self) -> None:
        masked = pii.mask("邮箱 zhangsan@example.com")
        self.assertNotIn("zhangsan@example.com", masked)
        self.assertIn("***@example.com", masked)

    def test_scan_secrets(self) -> None:
        self.assertTrue(pii.scan_secrets('const key = "sk-abcdefghijklmnopqrstuvwx"'))
        self.assertTrue(pii.scan_secrets("password: hunter2hunter2"))
        self.assertTrue(pii.scan_secrets("-----BEGIN RSA PRIVATE KEY-----"))
        self.assertFalse(pii.scan_secrets("const count = ref(0)"))


if __name__ == "__main__":
    unittest.main()
