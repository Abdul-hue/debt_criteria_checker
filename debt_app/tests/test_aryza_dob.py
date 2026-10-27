"""
D7: CaseData.dob is the client's calendar date of birth, whatever timezone the
server runs in.

Aryza stores client.dob as a Unix timestamp of midnight UK time -- 23:00 UTC
during British Summer Time, 00:00 UTC otherwise. AryzaClient used
datetime.fromtimestamp(), which converts in the SERVER's timezone: in a UTC
container every BST birthday came out a day early (and on Windows pre-1970
values raised and became None). It now converts in Europe/London.
"""
import os
import time
import unittest
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from debt_app import aryza_client
from debt_app.aryza_client import AryzaClient, CaseData, aryza_dob_to_date

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _ts(utc_datetime):
    return int((utc_datetime - EPOCH).total_seconds())


# Midnight UK time, as Aryza stores it.
BST_BIRTHDAY = _ts(datetime(1980, 7, 14, 23, 0, tzinfo=timezone.utc))      # 1980-07-15 00:00 BST
GMT_BIRTHDAY = _ts(datetime(1980, 1, 15, 0, 0, tzinfo=timezone.utc))       # 1980-01-15 00:00 GMT
PRE_1970 = _ts(datetime(1955, 3, 2, 0, 0, tzinfo=timezone.utc))            # 1955-03-02 00:00 GMT
BRITISH_STANDARD_TIME = _ts(datetime(1969, 12, 24, 23, 0, tzinfo=timezone.utc))  # 1969-12-25, UTC+1 all year


def _fetch_dob(timestamp):
    """CaseData.dob as AryzaClient._fetch_client_data sets it from a client row."""
    cursor = MagicMock()
    cursor.fetchone.side_effect = [(5, "Jane", "Doe", timestamp)] + [None] * 10
    cursor.fetchall.return_value = []
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    case = CaseData()
    AryzaClient()._fetch_client_data(connection, case, 5)
    return case.dob


class AryzaDobToDateTests(SimpleTestCase):

    def test_modern_bst_birthday(self):
        self.assertEqual(aryza_dob_to_date(BST_BIRTHDAY), date(1980, 7, 15))

    def test_modern_gmt_birthday(self):
        self.assertEqual(aryza_dob_to_date(GMT_BIRTHDAY), date(1980, 1, 15))

    def test_around_midnight(self):
        # Just after and just before UK midnight, in summer and winter.
        cases = {
            datetime(1990, 6, 30, 23, 30, tzinfo=timezone.utc): date(1990, 7, 1),    # 00:30 BST
            datetime(1990, 6, 30, 22, 59, tzinfo=timezone.utc): date(1990, 6, 30),   # 23:59 BST
            datetime(1990, 12, 1, 0, 30, tzinfo=timezone.utc): date(1990, 12, 1),    # 00:30 GMT
            datetime(1990, 11, 30, 23, 59, tzinfo=timezone.utc): date(1990, 11, 30), # 23:59 GMT
        }
        for moment, expected in cases.items():
            self.assertEqual(aryza_dob_to_date(_ts(moment)), expected, moment)

    def test_pre_1970(self):
        self.assertLess(PRE_1970, 0)
        self.assertEqual(aryza_dob_to_date(PRE_1970), date(1955, 3, 2))
        self.assertEqual(aryza_dob_to_date(BRITISH_STANDARD_TIME), date(1969, 12, 25))

    def test_missing_or_invalid(self):
        for value in (None, 0, "0", "", "x", 10 ** 20):
            self.assertIsNone(aryza_dob_to_date(value), value)

    def test_the_old_utc_conversion_was_a_day_early(self):
        # What fromtimestamp() gave in a UTC container -- the bug.
        self.assertEqual(datetime.fromtimestamp(BST_BIRTHDAY, tz=timezone.utc).date(), date(1980, 7, 14))


class CaseDataDobTests(SimpleTestCase):

    def test_case_dob_is_the_calendar_date(self):
        self.assertEqual(_fetch_dob(BST_BIRTHDAY), "1980-07-15")
        self.assertEqual(_fetch_dob(GMT_BIRTHDAY), "1980-01-15")
        self.assertEqual(_fetch_dob(PRE_1970), "1955-03-02")
        self.assertEqual(_fetch_dob(BRITISH_STANDARD_TIME), "1969-12-25")

    def test_case_dob_unset_stays_none(self):
        self.assertIsNone(_fetch_dob(None))
        self.assertIsNone(_fetch_dob(0))

    def test_case_dob_does_not_depend_on_the_server_timezone(self):
        # If anything still converted through the server's local timezone, this would raise.
        real = aryza_client.datetime

        class NoLocalConversion(real):
            @classmethod
            def fromtimestamp(cls, *args, **kwargs):
                raise AssertionError("dob must not be converted in the server's timezone")

        with patch.object(aryza_client, "datetime", NoLocalConversion):
            self.assertEqual(_fetch_dob(BST_BIRTHDAY), "1980-07-15")

    def test_identity_and_case_dob_agree(self):
        from debt_app.services.experian_credit_report import AryzaIdentity
        case = CaseData()
        case.first_name, case.last_name, case.dob_timestamp = "Jane", "Doe", BST_BIRTHDAY
        self.assertEqual(AryzaIdentity.from_case(case).date_of_birth.isoformat(), _fetch_dob(BST_BIRTHDAY))


@unittest.skipUnless(hasattr(time, "tzset"), "time.tzset() is unavailable on Windows")
class UtcContainerTests(SimpleTestCase):
    """Run the conversion with the process timezone set to UTC, as in the Docker image."""

    def setUp(self):
        self._old_tz = os.environ.get("TZ")
        os.environ["TZ"] = "UTC"
        time.tzset()

    def tearDown(self):
        if self._old_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._old_tz
        time.tzset()

    def test_bst_birthday_in_a_utc_process(self):
        self.assertEqual(_fetch_dob(BST_BIRTHDAY), "1980-07-15")
        self.assertEqual(_fetch_dob(PRE_1970), "1955-03-02")


class EuropeLondonProcessTests(SimpleTestCase):
    @unittest.skipUnless(hasattr(time, "tzset"), "time.tzset() is unavailable on Windows")
    def test_bst_birthday_in_a_london_process(self):
        old = os.environ.get("TZ")
        os.environ["TZ"] = "Europe/London"
        time.tzset()
        try:
            self.assertEqual(_fetch_dob(BST_BIRTHDAY), "1980-07-15")
        finally:
            if old is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = old
            time.tzset()

    def test_bst_birthday_in_this_process(self):
        # Whatever this machine's timezone is.
        self.assertEqual(_fetch_dob(BST_BIRTHDAY), "1980-07-15")
