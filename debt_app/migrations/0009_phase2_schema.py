# Generated manually for Phase 2 schema

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0008_seed_which_representative'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='creditorcriteria',
            name='status',
            field=models.CharField(
                choices=[
                    ('ACCEPT', 'Accept'),
                    ('REJECT', 'Reject'),
                    ('WILL_CONSIDER', 'Will Consider'),
                    ('DO_NOT_VOTE', 'Do Not Vote'),
                    ('CONDITIONAL_VOTER', 'Conditional Voter'),
                ],
                default='ACCEPT',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='reject_if_in_dmp',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='reject_if_never_made_payment',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='reject_if_ie_doesnt_match_application',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='reject_if_debt_repayable_within_months',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='reject_if_client_still_has_asset',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='reject_if_majority_share_exceeds_pct',
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=5, null=True
            ),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='reject_if_second_iva',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='reject_if_police_employed',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='reject_if_equity_exceeds_debt',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='requires_pg_called_up',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='requires_arrangement_call_before_proposing',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='requires_grant_overpayment_only',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='vehicle_arrears_repossession_months',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='fees_cap_percentage',
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=5, null=True
            ),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='termination_risk_if_vehicle_on_finance',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='conditional_voter',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='conditional_voter_min_dividend_pence',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='open_banking_access',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='min_di_for_fees_pence',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='fraud_claim_risk',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='blocked_until_cleared',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='blocked_reason',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='last_reviewed',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='criteriadecision',
            name='recommended_solution',
            field=models.CharField(
                choices=[
                    ('IVA', 'IVA - Individual Voluntary Arrangement'),
                    ('IVA NOT SUITABLE', 'IVA Not Suitable'),
                    ('IVA POSSIBLE', 'IVA Possible - Review Flagged Items'),
                    ('DMP', 'DMP - Debt Management Plan'),
                    ('FREE_SECTOR', 'Free Sector Solution'),
                    ('UNCLEAR', 'Unclear'),
                ],
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name='CouncilRule',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('council_name', models.CharField(max_length=255, unique=True)),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('ACCEPT', 'Accept'),
                            ('REJECT', 'Reject'),
                            ('WILL_CONSIDER', 'Will Consider'),
                            ('DO_NOT_VOTE', 'Do Not Vote'),
                            ('CONDITIONAL_VOTER', 'Conditional Voter'),
                        ],
                        default='WILL_CONSIDER',
                        max_length=20,
                    ),
                ),
                ('min_dividend_pence', models.IntegerField(blank=True, null=True)),
                ('reject_if_employed', models.BooleanField(default=False)),
                (
                    'reject_if_unemployed_and_homeowner',
                    models.BooleanField(default=False),
                ),
                ('reject_if_benefits_only', models.BooleanField(default=False)),
                ('reject_if_any_benefits', models.BooleanField(default=False)),
                ('reject_if_previous_iva', models.BooleanField(default=False)),
                ('reject_if_dro_criteria_met', models.BooleanField(default=False)),
                ('reject_if_aoe_in_place', models.BooleanField(default=False)),
                (
                    'reject_if_joint_one_party_only',
                    models.BooleanField(default=False),
                ),
                (
                    'reject_if_joint_both_parties',
                    models.BooleanField(default=False),
                ),
                (
                    'do_not_chase',
                    models.BooleanField(
                        default=False,
                        help_text=(
                            'If True, chasing this council converts status to REJECT'
                        ),
                    ),
                ),
                ('blocked_reason', models.TextField(blank=True, default='')),
                (
                    'source_priority',
                    models.IntegerField(
                        default=2,
                        help_text=(
                            '1=council sheet (authoritative), 2=dividends sheet'
                        ),
                    ),
                ),
                ('last_reviewed', models.DateField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Council Rule',
                'verbose_name_plural': 'Council Rules',
            },
        ),
        migrations.CreateModel(
            name='CountyCouncilRouting',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('county_name', models.CharField(max_length=255)),
                ('district_name', models.CharField(max_length=255)),
                (
                    'council_rule',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='county_routings',
                        to='debt_app.councilrule',
                    ),
                ),
            ],
            options={
                'verbose_name': 'County Council Routing',
                'verbose_name_plural': 'County Council Routings',
                'unique_together': {('county_name', 'district_name')},
            },
        ),
        migrations.CreateModel(
            name='DebtTypeCouncilVote',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'debt_type',
                    models.CharField(
                        choices=[
                            ('COUNCIL_TAX', 'Council Tax'),
                            ('PCN', 'Parking Charge Notice'),
                            ('HOUSING_BENEFIT', 'Housing Benefit'),
                        ],
                        max_length=50,
                    ),
                ),
                (
                    'status',
                    models.CharField(
                        choices=[
                            ('ACCEPT', 'Accept'),
                            ('REJECT', 'Reject'),
                            ('WILL_CONSIDER', 'Will Consider'),
                            ('DO_NOT_VOTE', 'Do Not Vote'),
                            ('CONDITIONAL_VOTER', 'Conditional Voter'),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    'council',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='debt_type_votes',
                        to='debt_app.councilrule',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Debt Type Council Vote',
                'verbose_name_plural': 'Debt Type Council Votes',
                'unique_together': {('council', 'debt_type')},
            },
        ),
        migrations.CreateModel(
            name='ConditionalVoterRule',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('min_dividend_pence', models.IntegerField(blank=True, null=True)),
                ('contact_required', models.BooleanField(default=False)),
                (
                    'contact_name',
                    models.CharField(blank=True, default='', max_length=255),
                ),
                (
                    'contact_email',
                    models.EmailField(blank=True, default='', max_length=254),
                ),
                (
                    'creditor',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='conditional_voter_rule',
                        to='debt_app.creditorcriteria',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Conditional Voter Rule',
                'verbose_name_plural': 'Conditional Voter Rules',
            },
        ),
        migrations.CreateModel(
            name='CreditorOpenBankingRule',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('review_period_months', models.IntegerField(default=3)),
                ('ie_must_match_exactly', models.BooleanField(default=False)),
                (
                    'creditor',
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='open_banking_rule',
                        to='debt_app.creditorcriteria',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Creditor Open Banking Rule',
                'verbose_name_plural': 'Creditor Open Banking Rules',
            },
        ),
    ]
