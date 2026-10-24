"""Payment evidence extraction cases from OCR text."""
import unittest
from intake import extract

class PaymentExtractionTests(unittest.TestCase):
    def test_gcash_reference_after_success_banner(self):
        draft, warnings = extract("G Cash\nTransaction Successful\nRef. No.\n1234567890123\nAmount Sent\nPHP 10,000.00\nSent to: Example Supplier\nOctober 24, 2026", "payment")
        self.assertEqual(draft["method"], "GCash")
        self.assertEqual(draft["reference"], "1234567890123")
        self.assertEqual(draft["amount"], "10000.00")
        self.assertEqual(draft["company"], "Example Supplier")

    def test_bank_transaction_id(self):
        draft, _ = extract("BPI InstaPay\nTransaction Successful\nTransaction ID: ABC123456789", "payment")
        self.assertEqual(draft["method"], "Bank")
        self.assertEqual(draft["reference"], "ABC123456789")

    def test_success_banner_is_not_a_reference(self):
        draft, warnings = extract("GCash\nTransaction Successful", "payment")
        self.assertEqual(draft["reference"], "")
        self.assertIn("Missing reference", warnings)
