import uuid
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class CreditorCriteria(models.Model):
    """Criteria and configuration for individual creditors."""

    REPRESENTATIVE_CHOICES = [
        ('WATCH', 'Watch'),
        ('TIX', 'TIX'),
        ('EVOLVE', 'Evolve'),
        ('NONE', 'None'),
    ]

    id = models.BigAutoField(primary_key=True)
    creditor_name = models.CharField(max_length=255, unique=True)

    trading_names = models.JSONField(
        blank=True,
        null=True,
        default=list,
        help_text="Alternative names creditor may appear under"
    )
    representative = models.CharField(
        max_length=10,
        choices=REPRESENTATIVE_CHOICES,
        default='NONE'
    )
    min_dividend_pence = models.IntegerField(
        blank=True,
        null=True,
        help_text="Minimum pence per pound they will accept (e.g., 30 = 30p/£1)"
    )
    contact_email = models.EmailField(blank=True, null=True)
    contact_phone = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    account_age_months = models.IntegerField(
        null=True,
        blank=True,
        help_text="Age of the account in months. Used for Shop Direct account age rules."
    )
    parent_group = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Banking group e.g. 'Lloyds Banking Group'"
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='creditor_criteria_updates'
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Creditor Criteria"
        indexes = [
            models.Index(fields=['creditor_name']),
            models.Index(fields=['representative']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return self.creditor_name


class GlobalCriteria(models.Model):
    """Global rules and thresholds for debt criteria assessment."""

    CRITERIA_SET_CHOICES = [
        ('TIG', 'TIG'),
        ('WATCH', 'Watch'),
        ('TIX', 'TIX'),
        ('EVOLVE', 'Evolve'),
    ]

    SEVERITY_CHOICES = [
        ('hard_block', 'Hard Block'),
        ('flag', 'Flag'),
        ('info', 'Info'),
    ]

    id = models.BigAutoField(primary_key=True)

    criteria_set = models.CharField(
        max_length=10,
        choices=CRITERIA_SET_CHOICES
    )
    rule_key = models.CharField(
        max_length=255,
        unique=True,
        help_text="Unique identifier for the rule (e.g., 'min_debt', 'watch_single_creditor')"
    )
    rule_name = models.CharField(max_length=255)
    severity = models.CharField(
        max_length=20,
        choices=SEVERITY_CHOICES
    )
    is_active = models.BooleanField(default=True)
    threshold_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Numeric threshold value for this rule"
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='global_criteria_updates'
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Global Criteria"
        indexes = [
            models.Index(fields=['rule_key']),
            models.Index(fields=['criteria_set']),
        ]

    def __str__(self):
        return f"{self.rule_key}: {self.rule_name}"


class Voter(models.Model):
    """Represents a voter in the system."""

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class Application(models.Model):
    """Debt application submitted for assessment."""

    id = models.BigAutoField(primary_key=True)
    aryza_reference = models.CharField(max_length=255, unique=True)
    client_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.client_name} ({self.aryza_reference})"


class EvidenceLedger(models.Model):
    """Audit log of evidence and decisions."""

    id = models.BigAutoField(primary_key=True)
    application = models.ForeignKey(
        Application,
        on_delete=models.CASCADE,
        related_name='evidence'
    )
    entry_type = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.application} - {self.entry_type}"


class CriteriaDecision(models.Model):
    """Audit log of criteria assessment decisions."""

    RECOMMENDED_SOLUTION_CHOICES = [
        ('IVA', 'IVA - Individual Voluntary Arrangement'),
        ('DMP', 'DMP - Debt Management Plan'),
        ('FREE_SECTOR', 'Free Sector Solution'),
        ('UNCLEAR', 'Unclear'),
    ]

    SOURCE_CHOICES = [
        ('STANDALONE', 'Standalone'),
        ('CASE_ASSESSMENT', 'Case Assessment'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Aryza reference"
    )
    client_name = models.CharField(max_length=255)
    input_snapshot = models.JSONField(
        help_text="Full data sent to criteria engine"
    )
    decision_output = models.JSONField(
        help_text="Full result from criteria engine"
    )
    recommended_solution = models.CharField(
        max_length=20,
        choices=RECOMMENDED_SOLUTION_CHOICES
    )
    passes_all_hard_blocks = models.BooleanField()
    triggered_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='criteria_decisions'
    )
    triggered_at = models.DateTimeField(auto_now_add=True, db_index=True)
    source = models.CharField(
        max_length=20,
        choices=SOURCE_CHOICES
    )

    class Meta:
        indexes = [
            models.Index(fields=['application_id']),
            models.Index(fields=['triggered_at']),
        ]

    def __str__(self):
        return f"Decision for {self.application_id} - {self.recommended_solution}"
