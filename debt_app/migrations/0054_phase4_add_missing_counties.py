"""
Phase 4 — add the 4 county councils present in the authoritative source
(Excel Criteria/County_Councils_Criteria.md) but absent from CountyCouncilRouting:
Derbyshire, Dorset, North Yorkshire, Staffordshire (32 districts).

The routing data + FK-pinning logic live in debt_app/seeds/county_routing.py
(shared with the seed_all_councils command). CouncilRule rows are seeded by that
command, not by migrations, so on a migration-only test/fresh DB the routing
rows are created with a null FK and pinning is deferred to the next
seed_all_councils run; on the live DB (councils present) they are pinned now.
See seeds/county_routing.py for the full rationale and the encoded decisions.
"""

from django.db import migrations

from debt_app.seeds.county_routing import seed_county_routing, COUNTIES


def forward(apps, schema_editor):
    CouncilRule = apps.get_model("debt_app", "CouncilRule")
    CountyCouncilRouting = apps.get_model("debt_app", "CountyCouncilRouting")
    created, pinned = seed_county_routing(
        CouncilRule, CountyCouncilRouting, log=lambda m: print("\n  " + m)
    )


def reverse(apps, schema_editor):
    CountyCouncilRouting = apps.get_model("debt_app", "CountyCouncilRouting")
    deleted, _ = CountyCouncilRouting.objects.filter(county_name__in=COUNTIES).delete()
    print(f"\n  Phase 4 reverse: removed {deleted} county routing row(s).")


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0053_seed_admiral_advantage_ccj_aoe"),
    ]

    operations = [
        migrations.RunPython(forward, reverse_code=reverse),
    ]
