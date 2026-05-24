import unittest
import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'debt_project.settings')
django.setup()

from debt_app.helpers import normalise_creditor_name

class TestCreditorNormalization(unittest.TestCase):
    def test_normalise_creditor_name(self):
        test_cases = [
            ("Zopa Limited", "zopa"),
            ("Gracombex Ltd T/A The Money Platform", "the money platform"),
            ("Madison CF UK Ltd T/A 118 118 Money", "118 118 money"),
            ("Barclays Bank Plc", "barclays bank"),
            ("Capital One Bank (Europe) Plc", "capital one bank"),
            ("STELLANTIS FINANCIAL SERVICES UK LIMITED", "stellantis financial services"),
            ("Admiral Financial Services LTD", "admiral financial services"),
            ("Link Financial Outsourcing Limited", "link financial outsourcing"),
            ("Barclays", "barclays"),
            ("HSBC Bank UK", "hsbc bank"),
            ("Shop Direct Finance Company LTD", "shop direct finance company"),
            ("Pay Later Group Limited", "pay later"),
        ]

        for input_name, expected in test_cases:
            with self.subTest(input_name=input_name):
                result = normalise_creditor_name(input_name)
                self.assertEqual(result, expected, f"Failed for '{input_name}': expected '{expected}', got '{result}'")

if __name__ == "__main__":
    unittest.main()
