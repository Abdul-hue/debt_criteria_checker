# Generated manually to change CreditorNonAcceptMilestone from a
# mixed-status daily milestone to a per-status daily milestone.
#
# Reasoning:
# - The feature has not shipped to production / seen real usage yet, so
#   any existing CreditorNonAcceptMilestone rows (all from local testing)
#   are dropped rather than backfilled with a synthetic `status` value.
# - status_breakdown (JSONField) is replaced with a plain `status`
#   CharField + `count` IntegerField. Now that each milestone always
#   describes a single status, a dict like {"rejected": 3} carries no
#   information beyond a (status, count) pair, so the simpler typed
#   columns are preferred over a JSON blob.
from django.db import migrations, models


def drop_existing_milestones(apps, schema_editor):
    CreditorNonAcceptMilestone = apps.get_model('debt_app', 'CreditorNonAcceptMilestone')
    CreditorNonAcceptMilestone.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0067_creditornonacceptmilestone'),
    ]

    operations = [
        migrations.RunPython(drop_existing_milestones, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='creditornonacceptmilestone',
            name='uniq_nonaccept_milestone_per_day',
        ),
        migrations.RemoveField(
            model_name='creditornonacceptmilestone',
            name='status_breakdown',
        ),
        migrations.AddField(
            model_name='creditornonacceptmilestone',
            name='status',
            field=models.CharField(
                choices=[
                    ('accepted', 'Accepted'),
                    ('rejected', 'Rejected'),
                    ('modified', 'Modified'),
                    ('pod', 'POD'),
                ],
                default='rejected',
                max_length=20,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='creditornonacceptmilestone',
            name='count',
            field=models.IntegerField(default=3),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name='creditornonacceptmilestone',
            constraint=models.UniqueConstraint(
                fields=('vote_summary', 'milestone_date', 'status'),
                name='uniq_nonaccept_milestone_per_day_status',
            ),
        ),
    ]
