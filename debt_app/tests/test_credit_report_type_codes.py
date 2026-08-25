"""
Regression tests for Aryza Advize account-block splitting by type code.

Bug this pins down
------------------
`_TYPE_CODE_RE` is the ONLY thing that marks where one account block ends and
the next begins. When a report used a type code missing from that regex, the
header did not start a new block, so the account's whole body was appended to
the PREVIOUS account's block. `_extract_field()` returns only the first match in
a block, so the unlisted account's "Current Balance" was silently discarded and
the account never appeared in the output at all.

Two symptoms, both covered below:
  1. the unlisted account (and its balance) vanishes entirely
  2. the PRECEDING account is corrupted — it inherits the swallowed account's
     payment-history grid, so worst_status / payment_history_months /
     missed_payments_last_3_months are computed over two accounts' rows

Codes found missing against 200 production reports: DP (Klarna BNPL), EW
(water), EE (electricity), IL (advance against income / payday), BK (basic bank
account). Together they accounted for 48 dropped accounts.

The layouts below are copied from real reports (currency symbols and column
ordering included) rather than invented, so they exercise the same text
pdfplumber actually produces. No PDF fixtures: media/ is gitignored.
"""
from django.test import SimpleTestCase

from debt_app.integrations.credit_report import (
    RECONCILIATION_ONLY_TYPE_CODES,
    _ARYZA_FALLBACK_HEADER_RE,
    _TYPE_CODE_RE,
    _parse_account_block,
    _split_into_account_blocks,
)


def _account(name, code, balance, *, start="2021-04-17", status="Up to date Good",
             years=("2026",), missed="0 0 0"):
    """
    One Aryza account block, mirroring real pdfplumber output.

    `years` and `missed` are parameterised so a swallowed block contributes
    payment-grid rows the preceding account did not have. Without that, every
    synthetic block would carry the same single year and the pollution assertions
    below would pass even against the buggy splitter.
    """
    grid = []
    for year in years:
        grid += [
            f"£{balance} £{balance} £{balance}",
            f"{year} - - - - - - - - -",
            missed,
        ]
    return "\n".join([
        f"{name} {code}",
        "Account Details:",
        "Account Type: Budget Account",
        "Account Status",
        f"Account Status: {status}",
        "Subjective Level:",
        "Credit Limit: N/A Payments: Monthly",
        "Minimum Payment: No Promotional Rate: No",
        "Balances Dates",
        f"Current Balance: £{balance} Last Update: 2026-08-01",
        f"Start Balance: £56 Start Date: {start}",
        "Default Balance: N/A End Date: N/A",
        "Balance",
        "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec",
        *grid,
    ])


# Codes that were missing and the account type each denotes in the real reports.
NEWLY_SUPPORTED = [
    ("DP", "Klarna Pay Later And Pay In 3", "79"),
    ("EW", "Yorkshire Water LTD", "1342"),
    ("EE", "British Gas - Electric", "1155"),
    ("IL", "Gracombex LTD T/A The Money Platform", "756"),
    ("BK", "HSBC Bank", "0"),
]


class TypeCodeRegexTests(SimpleTestCase):
    def test_previously_missing_codes_are_recognised(self):
        for code, name, _bal in NEWLY_SUPPORTED:
            with self.subTest(code=code):
                m = _TYPE_CODE_RE.match(f"{name} {code}")
                self.assertIsNotNone(m, f"{code} not matched by _TYPE_CODE_RE")
                self.assertEqual(m.group(1), name)
                self.assertEqual(m.group(2), code)

    def test_originally_supported_codes_still_match(self):
        """Guard against the additive edit breaking an existing code."""
        for code in ("CC", "UL", "MG", "MO", "CA", "UT", "PL",
                     "HP", "ST", "OT", "TM", "BD", "MI", "MU"):
            with self.subTest(code=code):
                m = _TYPE_CODE_RE.match(f"Some Creditor Ltd {code}")
                self.assertIsNotNone(m)
                self.assertEqual(m.group(2), code)

    def test_name_containing_a_type_code_is_not_truncated(self):
        """
        "Ee Limited TM" is a real header: the *name* starts with a code-like
        token. The non-greedy name group plus the `$` anchor must still take TM
        as the code and keep the full name.
        """
        m = _TYPE_CODE_RE.match("Ee Limited TM")
        self.assertEqual((m.group(1), m.group(2)), ("Ee Limited", "TM"))


class FallbackHeaderTests(SimpleTestCase):
    """
    The fallback is what stops the NEXT unknown code from silently deleting an
    account. It is deliberately loose, so these tests pin the guard rails.
    """

    def test_unknown_code_is_split_into_its_own_block(self):
        text = "\n".join([
            _account("Scottishpower Energy Retail Limited", "UT", "2698"),
            _account("Some New Tradeline Ltd", "ZZ", "4321"),
        ])
        blocks = _split_into_account_blocks(text)
        self.assertEqual(len(blocks), 2)
        self.assertEqual(blocks[1][0], "Some New Tradeline Ltd ZZ")

        parsed = _parse_account_block(*blocks[1])
        self.assertIsNotNone(parsed, "unknown-code block must still parse")
        self.assertEqual(parsed["type_code"], "ZZ")
        self.assertEqual(parsed["current_balance"], 432100)

    def test_fallback_ignores_lines_without_an_account_details_follower(self):
        """
        Payment-grid rows, address lines and section labels must never be taken
        for headers. The "Account Details" follower is the discriminator.
        """
        text = "\n".join([
            _account("Real Creditor Ltd", "CC", "185"),
            # None of the following should open a new block.
            "Current Address: 26 Cosford Garth, Bransholme, Hull HU7 4LD",
            "Some Trailing Label AB",
            "2026 £1,800 £1,800 £1,800",
            "0 0 0 0 0 0",
        ])
        blocks = _split_into_account_blocks(text)
        self.assertEqual(len(blocks), 1)

    def test_fallback_pattern_rejects_lines_with_a_colon(self):
        """Field lines like "Account Status: Up to date Good" must not match."""
        for line in (
            "Account Status: Late payment Bad",
            "Credit Limit: N/A Payments: Monthly",
            "Current Balance: £412 Last Update: 2026-08-01",
        ):
            with self.subTest(line=line):
                self.assertIsNone(_ARYZA_FALLBACK_HEADER_RE.match(line))


class SwallowedAccountTests(SimpleTestCase):
    """End-to-end: the two symptoms of the original bug."""

    def test_all_accounts_are_split_out_with_their_own_balance(self):
        text = "\n".join(
            [_account("Scottishpower Energy Retail Limited", "UT", "2698")]
            + [_account(name, code, bal) for code, name, bal in NEWLY_SUPPORTED]
        )
        blocks = _split_into_account_blocks(text)
        self.assertEqual(len(blocks), 1 + len(NEWLY_SUPPORTED))

        parsed = [_parse_account_block(h, b) for h, b in blocks]
        self.assertNotIn(None, parsed)

        by_code = {p["type_code"]: p for p in parsed}
        self.assertEqual(by_code["UT"]["current_balance"], 269800)
        for code, _name, bal in NEWLY_SUPPORTED:
            with self.subTest(code=code):
                self.assertEqual(
                    by_code[code]["current_balance"], int(bal) * 100,
                    f"{code} balance not extracted",
                )

    def test_preceding_account_is_not_polluted_by_the_next_block(self):
        """
        Symptom 2. Before the fix, Scottishpower's block absorbed the following
        accounts' payment grids, inflating payment_history_months (observed 84
        instead of 36 on a real report). This is worse than a blank field
        because it looks like valid data.
        """
        solo = _account("Scottishpower Energy Retail Limited", "UT", "2698")
        alone = _parse_account_block(*_split_into_account_blocks(solo)[0])
        # Sanity-check the fixture itself: if the trailing accounts contributed
        # no distinct grid rows, the assertions below would be vacuous.
        self.assertEqual(alone["payment_history_months"], 12)

        # Distinct years and a defaulted marker, so absorbing these blocks
        # measurably changes the first account's derived fields.
        followed = "\n".join([solo] + [
            _account(name, code, bal,
                     years=("2025", "2024", "2023"), missed="D D D")
            for code, name, bal in NEWLY_SUPPORTED
        ])
        first = _parse_account_block(*_split_into_account_blocks(followed)[0])

        for field in ("payment_history_months", "worst_status",
                      "missed_payments_last_3_months", "current_balance"):
            with self.subTest(field=field):
                self.assertEqual(
                    first[field], alone[field],
                    f"{field} changed when a later account followed — "
                    f"the block is still absorbing the next account",
                )


class ReconciliationRoutingTests(SimpleTestCase):
    def test_basic_bank_account_is_reconciliation_only(self):
        """
        BK is a bank account, not borrowing. It must not be counted as
        unsecured IVA debt just because it is now recognised.
        """
        self.assertIn("BK", RECONCILIATION_ONLY_TYPE_CODES)
        blocks = _split_into_account_blocks(_account("HSBC Bank", "BK", "0"))
        parsed = _parse_account_block(*blocks[0])
        self.assertTrue(parsed["reconciliation_only"])

    def test_debt_codes_are_not_reconciliation_only(self):
        """DP/IL are genuine unsecured debt; EW/EE are utilities like UT."""
        for code, name, bal in NEWLY_SUPPORTED:
            if code == "BK":
                continue
            with self.subTest(code=code):
                blocks = _split_into_account_blocks(_account(name, code, bal))
                parsed = _parse_account_block(*blocks[0])
                self.assertFalse(
                    parsed["reconciliation_only"],
                    f"{code} must count as unsecured debt",
                )
