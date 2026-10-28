"""
Add the GlobalCriteria rows for the Case Rejection Criteria (Missing Evidence)
rules, all SWITCHED OFF.

The rules read evidence fields CAT does not send yet (CA_TOOL_DEPENDENCIES.md,
"Proposed: Case Rejection Criteria"). Switched on they would flag every case
in scope for "evidence not known", so each one is switched on through an
approved Criteria Change once CAT sends its field.

get_or_create on these keys only — deliberately NOT a seed_rule_meta re-run,
which would reset is_active on every other rule. Mirrors the seed_rule_meta.py
source-of-truth entries.
"""

from django.db import migrations

RULES = [
    {
        "rule_key": "HMRC-CALL-SHEET",
        "rule_name": "HMRC debt requires a call sheet",
        "severity": "hard_block",
        "category": "hmrc",
        "description": "Any case with HMRC debt requires a completed call sheet.",
        "action": "Complete the call sheet and record it in CAT.",
    },
    {
        "rule_key": "SELF-EMPLOYED-CALL-SHEET",
        "rule_name": "Self-employed 12 months or longer requires a call sheet",
        "severity": "hard_block",
        "category": "income",
        "description": "A call sheet is mandatory where the client has been self-employed for 12 months or longer.",
        "action": "Record the self-employment start date and complete the call sheet.",
    },
    {
        "rule_key": "ARREARS-CREDITOR-CALL",
        "rule_name": "Mortgage, rent and hire purchase arrears require a creditor call",
        "severity": "hard_block",
        "category": "creditor_specific",
        "description": (
            "Each mortgage arrears, rent arrears and hire purchase creditor needs a creditor call confirming "
            "the outstanding arrears and any repayment arrangement (for rent, also whether the arrears can be "
            "included in the IVA)."
        ),
        "action": "Call each listed creditor and record the call in CAT.",
    },
    {
        "rule_key": "DEBT-LEVEL-EVIDENCED",
        "rule_name": "Evidenced debt must meet the IVA debt level",
        "severity": "hard_block",
        "category": "proof_of_debts",
        "description": (
            "The debt backed by proof of debt (or a credit report match) must meet the IVA minimum debt level. "
            "If it does not, the case is returned."
        ),
        "action": "Obtain proof of debt until the evidenced debt meets the minimum.",
    },
    {
        "rule_key": "POD-OVER-500",
        "rule_name": "Debts over £500 require proof of debt",
        "severity": "flag",
        "category": "proof_of_debts",
        "description": (
            "Debts over £500 require proof of debt. The case can proceed to drafting without individual PODs "
            "if the overall debt level is evidenced."
        ),
        "action": "Obtain proof of debt for each listed debt.",
    },
    {
        "rule_key": "COUNCIL-TAX-EVIDENCE",
        "rule_name": "Council tax evidence by council voting position",
        "severity": "hard_block",
        "category": "proof_of_debts",
        "description": (
            "Non-voting councils require proof of debt. Accepting, rejecting and DIV councils require a call "
            "sheet before SIP."
        ),
        "action": "Obtain the proof of debt or call sheet each listed council needs.",
    },
    {
        "rule_key": "CCJ-ORIGINAL-CREDITOR",
        "rule_name": "CCJ majority requires the original creditor",
        "severity": "hard_block",
        "category": "proof_of_debts",
        "description": "Where CCJs make up the majority of the debt, the original creditor of each CCJ must be identified.",
        "action": "Identify and record the original creditor for each listed CCJ.",
    },
]


def forward(apps, schema_editor):
    GlobalCriteria = apps.get_model("debt_app", "GlobalCriteria")
    for rule in RULES:
        defaults = {k: v for k, v in rule.items() if k != "rule_key"}
        GlobalCriteria.objects.get_or_create(
            rule_key=rule["rule_key"],
            defaults={**defaults, "criteria_set": "TIG", "is_active": False},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0093_creditreport_identity_mismatch_status"),
    ]

    # Reverse is a no-op: deleting the rows makes Django collect GlobalCriteria's
    # related objects through the historical model state, which fails when tests
    # migrate back past this point (test_credit_report_source). The rows are
    # switched off and forward is idempotent (get_or_create), so leaving them is safe.
    operations = [
        migrations.RunPython(forward, reverse_code=migrations.RunPython.noop),
    ]
