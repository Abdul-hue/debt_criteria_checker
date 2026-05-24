# Generated migration for adding documentation fields to GlobalCriteria

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0034_add_council_contact_and_criteria_changed_fields'),
    ]

    operations = [
        # Add documentation fields
        migrations.AddField(
            model_name='globalcriteria',
            name='description',
            field=models.TextField(blank=True, null=True, help_text='Detailed description of what this rule does'),
        ),
        migrations.AddField(
            model_name='globalcriteria',
            name='implementation_notes',
            field=models.TextField(blank=True, null=True, help_text='Technical implementation details'),
        ),
        migrations.AddField(
            model_name='globalcriteria',
            name='example_case',
            field=models.TextField(blank=True, null=True, help_text='Real-world example scenario'),
        ),
        migrations.AddField(
            model_name='globalcriteria',
            name='rejection_message',
            field=models.TextField(blank=True, null=True, help_text='User-facing message if rule results in rejection'),
        ),
        migrations.AddField(
            model_name='globalcriteria',
            name='flag_message',
            field=models.TextField(blank=True, null=True, help_text='User-facing message if rule results in a flag'),
        ),

        # Add organization fields
        migrations.AddField(
            model_name='globalcriteria',
            name='category',
            field=models.CharField(
                blank=True,
                null=True,
                max_length=50,
                choices=[
                    ('income', 'Income'),
                    ('bank_statements', 'Bank Statements'),
                    ('proof_of_debts', 'Proof of Debts'),
                    ('creditor_specific', 'Creditor Specific'),
                    ('hmrc', 'HMRC'),
                    ('vehicle', 'Vehicle'),
                    ('flags', 'Flags'),
                    ('other', 'Other'),
                ],
                help_text='Category for organizing rules'
            ),
        ),
        migrations.AddField(
            model_name='globalcriteria',
            name='is_creditor_specific',
            field=models.BooleanField(default=False, help_text='Whether this rule only applies to specific creditors'),
        ),
        migrations.AddField(
            model_name='globalcriteria',
            name='applies_to_creditors',
            field=models.JSONField(blank=True, null=True, default=list, help_text='List of creditor names this rule applies to'),
        ),
        migrations.AddField(
            model_name='globalcriteria',
            name='execution_order',
            field=models.IntegerField(blank=True, null=True, help_text='Order in which this rule should be evaluated'),
        ),

        # Add reference fields
        migrations.AddField(
            model_name='globalcriteria',
            name='references',
            field=models.JSONField(blank=True, null=True, default=list, help_text='List of documentation references (file paths, URLs, etc.)'),
        ),
        migrations.AddField(
            model_name='globalcriteria',
            name='related_rules',
            field=models.JSONField(blank=True, null=True, default=list, help_text='List of related rule keys (e.g., ["TIG-01", "TIG-02"])'),
        ),
        migrations.AddField(
            model_name='globalcriteria',
            name='depends_on_rules',
            field=models.JSONField(blank=True, null=True, default=list, help_text='List of rule keys this rule depends on'),
        ),

        # Add review fields
        migrations.AddField(
            model_name='globalcriteria',
            name='last_reviewed',
            field=models.DateField(blank=True, null=True, help_text='Date when this rule was last reviewed'),
        ),
        migrations.AddField(
            model_name='globalcriteria',
            name='review_notes',
            field=models.TextField(blank=True, null=True, help_text='Administrative notes from latest review'),
        ),

        # Add indexes for new fields
        migrations.AddIndex(
            model_name='globalcriteria',
            index=models.Index(fields=['category'], name='debt_app_globalcriteria_category_idx'),
        ),
        migrations.AddIndex(
            model_name='globalcriteria',
            index=models.Index(fields=['is_active'], name='debt_app_globalcriteria_is_active_idx'),
        ),
    ]
