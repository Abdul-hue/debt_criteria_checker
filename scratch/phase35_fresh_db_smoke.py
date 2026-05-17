"""Phase 3.5 fresh-DB smoke queries. Run: python scratch/phase35_fresh_db_smoke.py <db_path>"""
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")

if len(sys.argv) > 1:
    import importlib
    _settings_mod = importlib.import_module("debt_project.settings")
    _settings_mod.DATABASES["default"]["NAME"] = Path(sys.argv[1]).resolve()

import django

django.setup()

from django.conf import settings
from django.db import connection

from debt_app.models import (
    ClientFlags,
    ConditionalVoterRule,
    CouncilRule,
    CountyCouncilRouting,
    CreditorCriteria,
    CreditorOpenBankingRule,
    DebtTypeCouncilVote,
    Voter,
)

VOTER_PHASE3_FIELDS = [
    "is_joint",
    "last_payment_date",
    "first_payment_made",
    "vehicle_arrears_months",
    "ie_matches_loan_application",
    "arrangement_confirmed_before_proposing",
    "client_still_has_asset_in_possession",
    "is_grant_overpayment",
    "guarantee_called_up",
]


def main():
    db_path = settings.DATABASES["default"]["NAME"]
    print(f"DB: {db_path}")
    print(f"Tables: {connection.introspection.table_names()[:5]}... ({len(connection.introspection.table_names())} total)")

    cc_total = CreditorCriteria.objects.count()
    moneybarn = CreditorCriteria.objects.filter(creditor_name="Moneybarn").first()
    dmp_count = CreditorCriteria.objects.filter(reject_if_in_dmp=True).count()
    routing_count = CountyCouncilRouting.objects.count()

    print(f"CreditorCriteria total: {cc_total} (>= 13: {cc_total >= 13})")
    print(
        f"Moneybarn ACCEPT: {moneybarn is not None and moneybarn.status == 'ACCEPT'}"
        if moneybarn
        else "Moneybarn ACCEPT: False (row missing)"
    )
    print(f"reject_if_in_dmp count: {dmp_count} (>= 2: {dmp_count >= 2})")
    print(f"CountyCouncilRouting count: {routing_count} (~180: {150 <= routing_count <= 210})")

    for model in (
        CouncilRule,
        CountyCouncilRouting,
        DebtTypeCouncilVote,
        ConditionalVoterRule,
        CreditorOpenBankingRule,
        ClientFlags,
    ):
        print(f"Importable {model.__name__}: OK")

    for fname in VOTER_PHASE3_FIELDS:
        Voter._meta.get_field(fname)
        print(f"Voter field {fname}: OK")


if __name__ == "__main__":
    main()
