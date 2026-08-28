"""
Phase 4 — pin the council_rule FK on existing CountyCouncilRouting rows whose
abbreviated district_name doesn't resolve to a CouncilRule by name but has a
single unambiguous rule (12 of the 18 previously-unresolved districts).

Data + logic live in debt_app/seeds/county_routing.py (shared with the
seed_all_councils command). CouncilRule rows are seeded by that command, not by
migrations, so on a migration-only test/fresh DB unmatched pins are deferred to
the next seed_all_councils run; on the live DB they pin now. The remaining 6
districts (seeds.county_routing.UNPINNED_NO_RULE) have no rule anywhere and are
intentionally left as "manual review required".
"""

from django.db import migrations

from debt_app.seeds.county_routing import apply_alias_pins


def forward(apps, schema_editor):
    CouncilRule = apps.get_model("debt_app", "CouncilRule")
    CountyCouncilRouting = apps.get_model("debt_app", "CountyCouncilRouting")
    apply_alias_pins(
        CouncilRule, CountyCouncilRouting, log=lambda m: print("\n  " + m)
    )


def reverse(apps, schema_editor):
    # Un-pin only the alias rows (leave the row itself intact for name fallback).
    from debt_app.seeds.county_routing import ALIAS_PINS
    CountyCouncilRouting = apps.get_model("debt_app", "CountyCouncilRouting")
    n = 0
    for county, district, _tokens, _expected in ALIAS_PINS:
        n += CountyCouncilRouting.objects.filter(
            county_name=county, district_name=district
        ).update(council_rule=None)
    print(f"\n  Phase 4 reverse: un-pinned {n} alias routing row(s).")


class Migration(migrations.Migration):

    dependencies = [
        ("debt_app", "0054_phase4_add_missing_counties"),
    ]

    operations = [
        migrations.RunPython(forward, reverse_code=reverse),
    ]
