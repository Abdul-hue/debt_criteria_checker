"""
Add PRA Group to the Debt Collectors list (manager, 2026-11-03).

A debt entered in Aryza as "PRA Group" is held by an agency; the original debt
is with the company PRA collects for (e.g. Barclaycard), so BPO-DEBT now flags
it for the advisor to answer or dismiss. Until now PRA was left out as a debt
purchaser (0085). Cabot, Lowell, Intrum and Lantern are NOT added -- they stay
valid creditors until the business decides otherwise.

The aliases are the PRA names already seen in Aryza and on credit reports, and
the two "PRA (Portfolio Recovery Associates)" criteria rows a name can resolve
to. ⚠️ "PRA-Barclays Bank BV23071IVB"-style portfolio names are NOT aliases:
each carries an account code, and they resolve to the seller's row; how they
are treated is still open (tests/test_phase6_orange_pra.py).

Same names as `Excel Criteria/dca/dca_collectors_import.csv`, so a later import
of that file reports PRA Group as unchanged. An existing PRA Group row only
gains the missing aliases: one an admin switched off stays off, as
`import_debt_collectors` keeps it.
"""

from django.db import migrations


NAME = "PRA Group"
ALIASES = [
    "PRA",
    "PRA Group (UK) Limited",
    "PRA Group (UK) Limited (TIX)",
    "PRA Group (UK) Limited 01/10",
    "PRA Group (UK) Ltd c/o WPM",
    "Portfolio Recovery Associates",
    "Portfolio Recovery",
    "PRA (Portfolio Recovery Associates) - IVA",
    "PRA (Portfolio Recovery Associates) - TD",
]
NOTES = "Added by migration 0098 (manager, 2026-11-03): an agency; the original debt is with another creditor."


def forward(apps, schema_editor):
    DebtCollector = apps.get_model("debt_app", "DebtCollector")
    dc = DebtCollector.objects.filter(name__iexact=NAME).first()
    if dc is None:
        DebtCollector.objects.create(name=NAME, aliases=list(ALIASES), notes=NOTES)
        return
    existing = dc.aliases if isinstance(dc.aliases, list) else []
    have = {a.lower() for a in existing if isinstance(a, str)}
    missing = [a for a in ALIASES if a.lower() not in have]
    if missing:
        dc.aliases = existing + missing
        dc.save(update_fields=["aliases", "updated_at"])


def reverse(apps, schema_editor):
    # Only the row this migration created; one that was already there stays.
    DebtCollector = apps.get_model("debt_app", "DebtCollector")
    DebtCollector.objects.filter(name=NAME, notes=NOTES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0097_tig01_min_debt_5400"),
    ]

    operations = [
        migrations.RunPython(forward, reverse_code=reverse),
    ]
