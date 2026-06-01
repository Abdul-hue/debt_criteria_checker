from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0044_deactivate_lowell_lantern_legacy_entries'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Department',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=255, unique=True)),
                ('slug', models.SlugField(max_length=255, unique=True)),
                ('description', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Department',
                'verbose_name_plural': 'Departments',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('department', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='members',
                    to='debt_app.department',
                )),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='profile',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'User Profile',
                'verbose_name_plural': 'User Profiles',
            },
        ),
        migrations.CreateModel(
            name='DepartmentRuleVisibility',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_visible', models.BooleanField(default=True)),
                ('department', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='rule_visibilities',
                    to='debt_app.department',
                )),
                ('rule_key', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='department_visibilities',
                    to='debt_app.globalcriteria',
                    to_field='rule_key',
                )),
            ],
            options={
                'verbose_name': 'Department Rule Visibility',
                'verbose_name_plural': 'Department Rule Visibilities',
            },
        ),
        migrations.AddConstraint(
            model_name='departmentRuleVisibility'.lower(),
            constraint=models.UniqueConstraint(
                fields=['department', 'rule_key'],
                name='unique_dept_rule_visibility',
            ),
        ),
        migrations.CreateModel(
            name='DepartmentCreditorVisibility',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_visible', models.BooleanField(default=True)),
                ('department', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='creditor_visibilities',
                    to='debt_app.department',
                )),
                ('creditor', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='department_visibilities',
                    to='debt_app.creditorcriteria',
                )),
            ],
            options={
                'verbose_name': 'Department Creditor Visibility',
                'verbose_name_plural': 'Department Creditor Visibilities',
            },
        ),
        migrations.AddConstraint(
            model_name='departmentcreditorvisibility',
            constraint=models.UniqueConstraint(
                fields=['department', 'creditor'],
                name='unique_dept_creditor_visibility',
            ),
        ),
        migrations.CreateModel(
            name='DepartmentCouncilVisibility',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_visible', models.BooleanField(default=True)),
                ('department', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='council_visibilities',
                    to='debt_app.department',
                )),
                ('council', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='department_visibilities',
                    to='debt_app.councilrule',
                )),
            ],
            options={
                'verbose_name': 'Department Council Visibility',
                'verbose_name_plural': 'Department Council Visibilities',
            },
        ),
        migrations.AddConstraint(
            model_name='departmentcouncilvisibility',
            constraint=models.UniqueConstraint(
                fields=['department', 'council'],
                name='unique_dept_council_visibility',
            ),
        ),
    ]
