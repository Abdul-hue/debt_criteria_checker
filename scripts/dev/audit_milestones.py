import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "debt_project.settings")
django.setup()

from debt_app.models import CreditorNonAcceptMilestone

rows = CreditorNonAcceptMilestone.objects.select_related(
    'vote_summary__creditor_criteria',
    'vote_summary__council_rule',
    'vote_summary__county_council'
).order_by('created_at')

print(f"Total rows: {rows.count()}")
print("-" * 100)

for r in rows:
    vs = r.vote_summary
    if vs.creditor_criteria:
        name = vs.creditor_criteria.creditor_name
    elif vs.council_rule:
        name = vs.council_rule.council_name
    elif vs.county_council:
        name = vs.county_council.county_name
    else:
        name = "(unknown)"
    created_str = r.created_at.strftime("%Y-%m-%d %H:%M:%S")
    print(f"id={r.id}  date={r.milestone_date}  creditor={name}  breakdown={r.status_breakdown}  created={created_str}")
