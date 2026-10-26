"""
Phase 9 creditor decisions (manager, 2026-10-21).

Three creditors with no Criteria row, each a separate company (Phase 8
investigation, by company number and UUID):

- Parkingeye Limited (05134454): DO NOT VOTE. Private parking charges, not a
  council PCN; "Car Parking Partnership (CPP)" (02920033) is another company.
- Quidie Limited t/a Fernovo (08110266): DO NOT VOTE.
- Propel Holdings UK T/A Quidmarket (Stagemount Ltd, 07259223): TIX. Its vote
  comes from the TIX rules like every TIX row; the stored status is the TIX
  rows' ACCEPT default, which the engine does not read for a represented row.

Name variants reach these rows through helpers.CREDITOR_ALIAS_MAP.

Two credit unions that are separate lenders:

- South Manchester Credit Union: REJECT (its existing workbook stance).
- Manchester Credit Union: REJECT if the loan was taken in the last 3 months -
  account_age_months = 3, the engine's existing loan-age rule (credit-report
  start date; an unverified age is flagged, never assumed). Outside that it
  keeps its own status (workbook: Will Consider).

Rows are created only when missing and an existing value is never
overwritten, so a row a manager has already set is left as it is.
"""

from django.db import migrations

NEW_ROWS = (
    ("Parkingeye Limited", "NONE", "DO_NOT_VOTE",
     "Phase 9 (manager 2026-10-21): DO NOT VOTE. Company 05134454. Private parking operator, not a council PCN."),
    ("Quidie Limited t/a Fernovo", "NONE", "DO_NOT_VOTE",
     "Phase 9 (manager 2026-10-21): DO NOT VOTE. Company 08110266. Not Quidmarket, not Quick Quid."),
    ("Propel Holdings UK T/A Quidmarket", "TIX", "ACCEPT",
     "Phase 9 (manager 2026-10-21): TIX criteria. Stagemount Ltd, company 07259223. Not Quidie, not Quick Quid."),
    ("South Manchester Credit Union", "NONE", "REJECT",
     "Separate lender from Manchester Credit Union. REJECT (manager 2026-10-21)."),
)
MANCHESTER_CU = "Manchester Credit Union"
LOAN_AGE_MONTHS = 3


def forwards(apps, schema_editor):
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")
    for name, representative, status, note in NEW_ROWS:
        if not CreditorCriteria.objects.filter(creditor_name__iexact=name).exists():
            CreditorCriteria.objects.create(
                creditor_name=name, representative=representative, status=status,
                is_active=True, criteria_notes=note,
            )
    mcu = CreditorCriteria.objects.filter(creditor_name__iexact=MANCHESTER_CU).order_by("id").first()
    if mcu is None:
        CreditorCriteria.objects.create(
            creditor_name=MANCHESTER_CU, representative="NONE", status="WILL_CONSIDER", is_active=True,
            account_age_months=LOAN_AGE_MONTHS,
            criteria_notes="REJECT if the loan was taken in the last 3 months (manager 2026-10-21).",
        )
    elif mcu.account_age_months is None:
        CreditorCriteria.objects.filter(pk=mcu.pk).update(account_age_months=LOAN_AGE_MONTHS)


def backwards(apps, schema_editor):
    CreditorCriteria = apps.get_model("debt_app", "CreditorCriteria")
    for name, representative, status, note in NEW_ROWS:
        CreditorCriteria.objects.filter(creditor_name=name, criteria_notes=note).delete()
    CreditorCriteria.objects.filter(
        creditor_name=MANCHESTER_CU, account_age_months=LOAN_AGE_MONTHS,
    ).update(account_age_months=None)


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0090_add_bank_statements_rule"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
