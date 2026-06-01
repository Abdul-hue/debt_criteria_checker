import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0045_departments_and_rule_visibility'),
    ]

    operations = [
        migrations.CreateModel(
            name='DepartmentSFSVisibility',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_visible', models.BooleanField(default=True)),
                ('department', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='sfs_visibilities',
                    to='debt_app.department',
                )),
                ('guideline', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='department_visibilities',
                    to='debt_app.expenditureguideline',
                )),
            ],
            options={
                'verbose_name': 'Department SFS Visibility',
                'verbose_name_plural': 'Department SFS Visibilities',
                'ordering': ['department', 'guideline'],
            },
        ),
        migrations.AlterUniqueTogether(
            name='departmentsfsvisibility',
            unique_together={('department', 'guideline')},
        ),
        migrations.CreateModel(
            name='DepartmentFeatureAccess',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('feature_key', models.CharField(
                    choices=[
                        ('general_creditors', 'General Creditors'),
                        ('representative_creditors', 'Representative Creditors'),
                        ('global_rules', 'Global Rules'),
                        ('councils', 'Councils'),
                        ('dividends', 'Dividends'),
                        ('sfs_guidelines', 'SFS Guidelines'),
                        ('run_assessment', 'Run Assessment'),
                        ('decisions', 'Decisions'),
                        ('evidence', 'Evidence'),
                        ('user_management', 'User Management'),
                    ],
                    max_length=50,
                )),
                ('is_enabled', models.BooleanField(default=True)),
                ('department', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='feature_accesses',
                    to='debt_app.department',
                )),
            ],
            options={
                'verbose_name': 'Department Feature Access',
                'verbose_name_plural': 'Department Feature Accesses',
            },
        ),
        migrations.AlterUniqueTogether(
            name='departmentfeatureaccess',
            unique_together={('department', 'feature_key')},
        ),
    ]
