import uuid
from datetime import date
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class CreditorCriteria(models.Model):
    """Criteria and configuration for individual creditors."""

    REPRESENTATIVE_CHOICES = [
        ('WATCH', 'Watch'),
        ('TIX', 'TIX'),
        ('EVOLVE', 'Evolve'),
        ('EVERYDAY_LOANS', 'Everyday Loans'),
        ('NONE', 'None'),
    ]

    STATUS_CHOICES = [
        ('ACCEPT', 'Accept'),
        ('REJECT', 'Reject'),
        ('WILL_CONSIDER', 'Will Consider'),
        ('DO_NOT_VOTE', 'Do Not Vote'),
        ('CONDITIONAL_VOTER', 'Conditional Voter'),
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
        max_length=15,
        choices=REPRESENTATIVE_CHOICES,
        default='NONE'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='ACCEPT',
    )
    min_dividend_pence = models.IntegerField(
        blank=True,
        null=True,
        help_text="Minimum pence per pound they will accept (e.g., 30 = 30p/£1)"
    )
    dividend_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Free-text notes for caseworkers about this creditor's dividend requirements",
    )
    contact_name = models.CharField(max_length=255, blank=True, null=True)
    contact_email = models.EmailField(blank=True, null=True)
    contact_phone = models.CharField(max_length=20, blank=True, null=True)
    criteria_notes = models.TextField(
        blank=True,
        null=True,
        help_text="General criteria notes for this creditor",
    )
    raw_updated_criteria = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Raw text from the 'updated criteria' column"
    )
    source_sheet = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="The Excel sheet this creditor was primarily sourced from"
    )
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

    # --- Rejection / conditional voting rules ---
    reject_if_in_dmp = models.BooleanField(default=False)
    reject_if_never_made_payment = models.BooleanField(default=False)
    reject_if_ie_doesnt_match_application = models.BooleanField(default=False)
    reject_if_debt_repayable_within_months = models.IntegerField(blank=True, null=True)
    reject_if_client_still_has_asset = models.BooleanField(default=False)
    reject_if_majority_share_exceeds_pct = models.DecimalField(
        blank=True, decimal_places=2, max_digits=5, null=True
    )
    reject_if_second_iva = models.BooleanField(default=False)
    reject_if_police_employed = models.BooleanField(default=False)
    reject_if_equity_exceeds_debt = models.BooleanField(default=False)

    # --- Requirements ---
    requires_pg_called_up = models.BooleanField(default=False)
    requires_arrangement_call_before_proposing = models.BooleanField(default=False)
    requires_grant_overpayment_only = models.BooleanField(default=False)

    # --- Financial thresholds ---
    vehicle_arrears_repossession_months = models.IntegerField(blank=True, null=True)
    fees_cap_percentage = models.DecimalField(
        blank=True, decimal_places=2, max_digits=5, null=True
    )
    min_di_for_fees_pence = models.IntegerField(blank=True, null=True)

    # --- Flags ---
    termination_risk_if_vehicle_on_finance = models.BooleanField(default=False)
    conditional_voter = models.BooleanField(default=False)
    conditional_voter_min_dividend_pence = models.IntegerField(blank=True, null=True)
    open_banking_access = models.BooleanField(default=False)
    fraud_claim_risk = models.BooleanField(default=False)
    blocked_until_cleared = models.BooleanField(default=False)
    blocked_reason = models.TextField(blank=True, default='')

    last_reviewed = models.DateField(blank=True, null=True)
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


class CreditorResolutionMiss(models.Model):
    raw_name = models.CharField(max_length=500)  # exact string Aryza sent
    normalised_name = models.CharField(max_length=500, blank=True)  # after normalisation
    case_reference = models.CharField(max_length=100)  # aryza_reference
    client_name = models.CharField(max_length=300, blank=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    logged_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False)  # set True once alias is added
    resolution_notes = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['-logged_at']
        indexes = [
            models.Index(fields=['raw_name']),
            models.Index(fields=['resolved', 'logged_at'])
        ]

    def __str__(self):
        return f"{self.raw_name} ({self.case_reference})"


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

    CATEGORY_CHOICES = [
        ('income', 'Income'),
        ('bank_statements', 'Bank Statements'),
        ('proof_of_debts', 'Proof of Debts'),
        ('creditor_specific', 'Creditor Specific'),
        ('hmrc', 'HMRC'),
        ('vehicle', 'Vehicle'),
        ('flags', 'Flags'),
        ('other', 'Other'),
    ]

    id = models.BigAutoField(primary_key=True)

    # --- Core fields ---
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

    # --- Documentation fields ---
    description = models.TextField(
        blank=True,
        null=True,
        help_text="Detailed description of what this rule does"
    )
    action = models.TextField(
        blank=True,
        null=True,
        help_text="Recommended action if this rule is triggered"
    )
    implementation_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Technical implementation details"
    )
    example_case = models.TextField(
        blank=True,
        null=True,
        help_text="Real-world example scenario"
    )
    rejection_message = models.TextField(
        blank=True,
        null=True,
        help_text="User-facing message if rule results in rejection"
    )
    flag_message = models.TextField(
        blank=True,
        null=True,
        help_text="User-facing message if rule results in a flag"
    )

    # --- Organization fields ---
    category = models.CharField(
        max_length=50,
        choices=CATEGORY_CHOICES,
        blank=True,
        null=True,
        help_text="Category for organizing rules"
    )
    is_creditor_specific = models.BooleanField(
        default=False,
        help_text="Whether this rule only applies to specific creditors"
    )
    applies_to_creditors = models.JSONField(
        blank=True,
        null=True,
        default=list,
        help_text="List of creditor names this rule applies to"
    )
    execution_order = models.IntegerField(
        blank=True,
        null=True,
        help_text="Order in which this rule should be evaluated"
    )

    # --- Reference fields ---
    references = models.JSONField(
        blank=True,
        null=True,
        default=list,
        help_text="List of documentation references (file paths, URLs, etc.)"
    )
    related_rules = models.JSONField(
        blank=True,
        null=True,
        default=list,
        help_text="List of related rule keys (e.g., ['TIG-01', 'TIG-02'])"
    )
    depends_on_rules = models.JSONField(
        blank=True,
        null=True,
        default=list,
        help_text="List of rule keys this rule depends on"
    )

    # --- Review fields ---
    last_reviewed = models.DateField(
        blank=True,
        null=True,
        help_text="Date when this rule was last reviewed"
    )
    review_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Administrative notes from latest review"
    )

    # --- Audit fields ---
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
            models.Index(fields=['category']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.rule_key}: {self.rule_name}"


class CouncilRule(models.Model):
    """Voting behaviour for individual councils."""

    STATUS_CHOICES = [
        ('ACCEPT', 'Accept'),
        ('REJECT', 'Reject'),
        ('WILL_CONSIDER', 'Will Consider'),
        ('DO_NOT_VOTE', 'Do Not Vote'),
        ('CONDITIONAL_VOTER', 'Conditional Voter'),
    ]

    council_name = models.CharField(max_length=255, unique=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='WILL_CONSIDER',
    )
    min_dividend_pence = models.IntegerField(blank=True, null=True)

    # Rejection conditions
    reject_if_employed = models.BooleanField(default=False)
    reject_if_unemployed_and_homeowner = models.BooleanField(default=False)
    reject_if_benefits_only = models.BooleanField(default=False)
    reject_if_any_benefits = models.BooleanField(default=False)
    reject_if_previous_iva = models.BooleanField(default=False)
    reject_if_dro_criteria_met = models.BooleanField(default=False)
    reject_if_aoe_in_place = models.BooleanField(default=False)
    reject_if_joint_one_party_only = models.BooleanField(default=False)
    reject_if_joint_both_parties = models.BooleanField(default=False)
    reject_if_sole = models.BooleanField(default=False)
    reject_if_joint_one_employed = models.BooleanField(default=False)

    do_not_chase = models.BooleanField(
        default=False,
        help_text='If True, chasing this council converts status to REJECT',
    )
    include_current_year_ct = models.BooleanField(default=False)
    blocked_reason = models.TextField(blank=True, default='')
    criteria_changed_from_rej_date = models.CharField(max_length=100, blank=True, default='')
    contact_name = models.CharField(max_length=255, blank=True, default='')
    contact_number = models.CharField(max_length=255, blank=True, default='')
    source_priority = models.IntegerField(
        default=2,
        help_text='1=council sheet (authoritative), 2=dividends sheet',
    )
    last_reviewed = models.DateField(blank=True, null=True)

    class Meta:
        verbose_name = 'Council Rule'
        verbose_name_plural = 'Council Rules'

    def __str__(self):
        return self.council_name


class CountyCouncilRouting(models.Model):
    """Routes a county+district combination to a CouncilRule."""

    county_name = models.CharField(max_length=255)
    district_name = models.CharField(max_length=255)
    council_rule = models.ForeignKey(
        CouncilRule,
        blank=True,
        null=True,
        on_delete=models.PROTECT,
        related_name='county_routings',
    )

    class Meta:
        verbose_name = 'County Council Routing'
        verbose_name_plural = 'County Council Routings'
        unique_together = [('county_name', 'district_name')]

    def __str__(self):
        return f"{self.county_name} / {self.district_name}"


class DebtTypeCouncilVote(models.Model):
    """Per-debt-type override for a CouncilRule's voting behaviour."""

    DEBT_TYPE_CHOICES = [
        ('COUNCIL_TAX', 'Council Tax'),
        ('PCN', 'Parking Charge Notice'),
        ('HOUSING_BENEFIT', 'Housing Benefit'),
    ]

    STATUS_CHOICES = [
        ('ACCEPT', 'Accept'),
        ('REJECT', 'Reject'),
        ('WILL_CONSIDER', 'Will Consider'),
        ('DO_NOT_VOTE', 'Do Not Vote'),
        ('CONDITIONAL_VOTER', 'Conditional Voter'),
    ]

    council = models.ForeignKey(
        CouncilRule,
        on_delete=models.CASCADE,
        related_name='debt_type_votes',
    )
    debt_type = models.CharField(max_length=50, choices=DEBT_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    class Meta:
        verbose_name = 'Debt Type Council Vote'
        verbose_name_plural = 'Debt Type Council Votes'
        unique_together = [('council', 'debt_type')]

    def __str__(self):
        return f"{self.council.council_name} — {self.debt_type}: {self.status}"


class ConditionalVoterRule(models.Model):
    """Supplementary conditional-voter configuration for a CreditorCriteria."""

    creditor = models.OneToOneField(
        CreditorCriteria,
        on_delete=models.CASCADE,
        related_name='conditional_voter_rule',
    )
    min_dividend_pence = models.IntegerField(blank=True, null=True)
    contact_required = models.BooleanField(default=False)
    contact_name = models.CharField(blank=True, default='', max_length=255)
    contact_email = models.EmailField(blank=True, default='', max_length=254)

    class Meta:
        verbose_name = 'Conditional Voter Rule'
        verbose_name_plural = 'Conditional Voter Rules'

    def __str__(self):
        return f"ConditionalVoterRule({self.creditor})"


class CreditorOpenBankingRule(models.Model):
    """Open-banking review requirements for a CreditorCriteria."""

    creditor = models.OneToOneField(
        CreditorCriteria,
        on_delete=models.CASCADE,
        related_name='open_banking_rule',
    )
    review_period_months = models.IntegerField(default=3)
    ie_must_match_exactly = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Creditor Open Banking Rule'
        verbose_name_plural = 'Creditor Open Banking Rules'

    def __str__(self):
        return f"OpenBankingRule({self.creditor})"


class Voter(models.Model):
    """Represents a creditor vote on a specific case."""

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)

    # Phase 3 fields
    is_joint = models.BooleanField(default=False)
    last_payment_date = models.DateField(blank=True, null=True)
    first_payment_made = models.BooleanField(default=False)
    vehicle_arrears_months = models.IntegerField(blank=True, null=True)
    ie_matches_loan_application = models.BooleanField(blank=True, null=True)
    arrangement_confirmed_before_proposing = models.BooleanField(default=False)
    client_still_has_asset_in_possession = models.BooleanField(default=False)
    is_grant_overpayment = models.BooleanField(default=False)
    guarantee_called_up = models.BooleanField(blank=True, null=True)

    @property
    def months_since_last_payment(self):
        """Months between last_payment_date and today. None if date not set or in the future."""
        if not self.last_payment_date:
            return None
        today = date.today()
        if self.last_payment_date > today:
            return None
        delta = today - self.last_payment_date
        return max(0, delta.days // 30)

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


class ClientFlags(models.Model):
    """Per-application flags about the client's situation."""

    application = models.OneToOneField(
        Application,
        on_delete=models.CASCADE,
        related_name='client_flags',
    )
    is_currently_in_dmp = models.BooleanField(default=False)
    is_royal_mail_employee = models.BooleanField(default=False)
    is_police_officer = models.BooleanField(default=False)
    previous_iva_failed = models.BooleanField(default=False)

    def __str__(self):
        return f"ClientFlags({self.application})"


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
        ('IVA NOT SUITABLE', 'IVA Not Suitable'),
        ('IVA POSSIBLE', 'IVA Possible - Review Flagged Items'),
        ('DMP', 'DMP - Debt Management Plan'),
        ('BREATHING_SPACE', 'Debt Respite Scheme (Breathing Space)'),
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
    result_json = models.JSONField(
        null=True,
        blank=True,
        help_text="Phase 1 standardized evaluation response"
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
