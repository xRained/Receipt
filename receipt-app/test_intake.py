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

    def test_spaced_gcash_reference_beside_timestamp(self):
        text="Sent via GCash\nAmount 25,133.48\nRef No. 1234 567 890123    Oct 23, 2026 10:48 AM"
        draft, _ = extract(text, 'payment')
        self.assertEqual(draft['reference'], '1234567890123')
        self.assertEqual(draft['method'], 'GCash')
        self.assertEqual(draft['amount'], '25133.48')
        self.assertEqual(draft['date'], '2026-10-23')

    def test_phone_number_is_not_gcash_reference(self):
        draft, warnings = extract('GCash\n+63 917 123 4567\nOct 23, 2026', 'payment')
        self.assertEqual(draft['reference'], '')
        self.assertIn('Missing reference', warnings)

    def test_total_amount_sent_with_ocr_dollar_symbol(self):
        draft,_=extract('Sent via GCash\nTotal Amount Sent $25,133.48\nRef No. 1234 567 890123', 'payment')
        self.assertEqual(draft['amount'],'25133.48')

    def test_explicit_trading_name_and_proprietor_text(self):
        draft,_=extract('Business Name: Example New Hardware\nExample New Owner - Prop.\nTotal Amount: 444.00', 'receipt')
        self.assertEqual(draft['company'],'Example New Owner - Prop.')
        self.assertEqual(draft['business_name'],'Example New Hardware')
