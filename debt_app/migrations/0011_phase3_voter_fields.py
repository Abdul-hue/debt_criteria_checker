# Phase 3 — Voter per-debt metadata fields

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0010_phase2_seeds'),
    ]

    operations = [
        migrations.AddField(
            model_name='voter',
            name='is_joint',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='voter',
            name='last_payment_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='voter',
            name='first_payment_made',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='voter',
            name='vehicle_arrears_months',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='voter',
            name='ie_matches_loan_application',
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='voter',
            name='arrangement_confirmed_before_proposing',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='voter',
            name='client_still_has_asset_in_possession',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='voter',
            name='is_grant_overpayment',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='voter',
            name='guarantee_called_up',
            field=models.BooleanField(blank=True, null=True),
        ),
    ]
