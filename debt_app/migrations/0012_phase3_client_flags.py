# Phase 3 — ClientFlags model (OneToOne to Application)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('debt_app', '0011_phase3_voter_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClientFlags',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True,
                    primary_key=True,
                    serialize=False,
                    verbose_name='ID',
                )),
                ('is_currently_in_dmp', models.BooleanField(default=False)),
                ('is_royal_mail_employee', models.BooleanField(default=False)),
                ('is_police_officer', models.BooleanField(default=False)),
                ('previous_iva_failed', models.BooleanField(default=False)),
                ('application', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='client_flags',
                    to='debt_app.application',
                )),
            ],
        ),
    ]
