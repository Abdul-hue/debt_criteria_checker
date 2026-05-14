# Generated migration file for extending criteria models
# This migration adds new fields to existing models and creates CriteriaDecision

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0001_initial'),  # Adjust to your actual last migration
    ]

    operations = [
        # Add new fields to CreditorCriteria
        migrations.AddField(
            model_name='creditorcriteria',
            name='trading_names',
            field=models.JSONField(
                blank=True,
                null=True,
                default=list,
                help_text='Alternative names creditor may appear under'
            ),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='representative',
            field=models.CharField(
                choices=[('WATCH', 'Watch'), ('TIX', 'TIX'), ('EVOLVE', 'Evolve'), ('NONE', 'None')],
                default='NONE',
                max_length=10
            ),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='min_dividend_pence',
            field=models.IntegerField(
                blank=True,
                null=True,
                help_text='Minimum pence per pound they will accept (e.g., 30 = 30p/£1)'
            ),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='contact_email',
            field=models.EmailField(blank=True, max_length=254, null=True),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='contact_phone',
            field=models.CharField(blank=True, max_length=20, null=True),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='is_watch',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='is_tix',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='is_evolve',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='parent_group',
            field=models.CharField(
                blank=True,
                max_length=255,
                null=True,
                help_text='Banking group e.g. "Lloyds Banking Group"'
            ),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='updated_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='creditor_criteria_updates',
                to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AddField(
            model_name='creditorcriteria',
            name='last_updated',
            field=models.DateTimeField(auto_now=True),
        ),
        
        # Add indexes to CreditorCriteria
        migrations.AddIndex(
            model_name='creditorcriteria',
            index=models.Index(fields=['name'], name='debt_app_creditorcriteria_name_idx'),
        ),
        migrations.AddIndex(
            model_name='creditorcriteria',
            index=models.Index(fields=['representative'], name='debt_app_creditorcriteria_representative_idx'),
        ),
        migrations.AddIndex(
            model_name='creditorcriteria',
            index=models.Index(fields=['is_active'], name='debt_app_creditorcriteria_is_active_idx'),
        ),
        
        # Add new fields to GlobalCriteria
        migrations.AddField(
            model_name='globalcriteria',
            name='criteria_set',
            field=models.CharField(
                choices=[('TIG', 'TIG'), ('WATCH', 'Watch'), ('TIX', 'TIX'), ('EVOLVE', 'Evolve')],
                default='TIG',
                max_length=10
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='globalcriteria',
            name='rule_key',
            field=models.CharField(
                default='temp_key',
                max_length=255,
                unique=True,
                help_text='Unique identifier for the rule'
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='globalcriteria',
            name='rule_name',
            field=models.CharField(default='Unnamed Rule', max_length=255),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='globalcriteria',
            name='severity',
            field=models.CharField(
                choices=[('hard_block', 'Hard Block'), ('flag', 'Flag'), ('info', 'Info')],
                default='info',
                max_length=20
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='globalcriteria',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='globalcriteria',
            name='threshold_value',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                help_text='Numeric threshold value for this rule'
            ),
        ),
        migrations.AddField(
            model_name='globalcriteria',
            name='updated_by',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='global_criteria_updates',
                to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AddField(
            model_name='globalcriteria',
            name='last_updated',
            field=models.DateTimeField(auto_now=True),
        ),
        
        # Add indexes to GlobalCriteria
        migrations.AddIndex(
            model_name='globalcriteria',
            index=models.Index(fields=['rule_key'], name='debt_app_globalcriteria_rule_key_idx'),
        ),
        migrations.AddIndex(
            model_name='globalcriteria',
            index=models.Index(fields=['criteria_set'], name='debt_app_globalcriteria_criteria_set_idx'),
        ),
        
        # Create CriteriaDecision model
        migrations.CreateModel(
            name='CriteriaDecision',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('application_id', models.CharField(db_index=True, help_text='Aryza reference', max_length=255)),
                ('client_name', models.CharField(max_length=255)),
                ('input_snapshot', models.JSONField(help_text='Full data sent to criteria engine')),
                ('decision_output', models.JSONField(help_text='Full result from criteria engine')),
                ('recommended_solution', models.CharField(
                    choices=[
                        ('IVA', 'IVA - Individual Voluntary Arrangement'),
                        ('DMP', 'DMP - Debt Management Plan'),
                        ('FREE_SECTOR', 'Free Sector Solution'),
                        ('UNCLEAR', 'Unclear'),
                    ],
                    max_length=20
                )),
                ('passes_all_hard_blocks', models.BooleanField()),
                ('triggered_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('source', models.CharField(
                    choices=[('STANDALONE', 'Standalone'), ('CASE_ASSESSMENT', 'Case Assessment')],
                    max_length=20
                )),
                ('triggered_by', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='criteria_decisions',
                    to=settings.AUTH_USER_MODEL
                )),
            ],
        ),
        
        # Add indexes to CriteriaDecision
        migrations.AddIndex(
            model_name='criteriadecision',
            index=models.Index(fields=['application_id'], name='debt_app_criteriadecision_application_id_idx'),
        ),
        migrations.AddIndex(
            model_name='criteriadecision',
            index=models.Index(fields=['triggered_at'], name='debt_app_criteriadecision_triggered_at_idx'),
        ),
    ]
