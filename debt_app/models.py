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
    reject_if_recent_spend_months = models.IntegerField(
        blank=True,
        null=True,
        help_text=(
            "Reject if client has had any transactions matching this "
            "creditor name in the last N months. Checked against "
            "gold_transactions in the case payload."
        ),
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
    reject_if_ccj = models.BooleanField(
        default=False,
        help_text="Reject if the client has a County Court Judgment on their credit report",
    )
    reject_if_aoe = models.BooleanField(
        default=False,
        help_text="Reject if an Attachment of Earnings order is already in place",
    )

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
    requires_credit_report = models.BooleanField(
        default=False,
        help_text="If True, engine emits FLAG when no credit report is uploaded"
    )
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


class CreditorOutcome(models.Model):
    OUTCOME_CHOICES = [
        ('approved', 'Approved'),
        ('disapproved', 'Disapproved'),
    ]

    creditor = models.ForeignKey(
        CreditorCriteria,
        on_delete=models.CASCADE,
        related_name='outcomes'
    )
    case_reference = models.CharField(max_length=50)
    outcome = models.CharField(max_length=20, choices=OUTCOME_CHOICES)
    outcome_date = models.DateField()
    comment = models.TextField(blank=True, default='')
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='creditor_outcomes'
    )
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f"{self.creditor.creditor_name} — {self.outcome} — {self.case_reference}"





class CriteriaAuditLog(models.Model):
    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
    ]

    creditor = models.ForeignKey(
        CreditorCriteria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs'
    )
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='criteria_audit_logs'
    )
    changed_at = models.DateTimeField(auto_now_add=True)
    field_name = models.CharField(max_length=100)
    old_value = models.TextField(blank=True, default='')
    new_value = models.TextField(blank=True, default='')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, default='update')

    class Meta:
        ordering = ['-changed_at']

    def __str__(self):
        return f"{self.creditor} — {self.field_name} — {self.changed_at}"


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


class CountyCouncil(models.Model):
    """
    The county-tier authority itself (e.g. Buckinghamshire County Council).

    Distinct from CouncilRule: a CouncilRule is a council-tax-collecting
    authority (district/borough/city/unitary). A CountyCouncil is the
    two-tier parent — in most cases it does NOT collect council tax itself
    (that's delegated to its districts, see CountyCouncilRouting) but can
    still have its own IVA voting criteria for other debt types.
    """

    # Most county councils have no voting behaviour of their own at all —
    # they delegate council tax entirely to their districts and are never
    # themselves a creditor. NO_CRITERIA reflects that honestly; the other
    # choices are only used for the rare county (e.g. Buckinghamshire) whose
    # ground-truth notes state actual accept/reject criteria.
    STATUS_CHOICES = [
        ('NO_CRITERIA', 'No Direct Criteria — delegates to districts'),
    ] + CouncilRule.STATUS_CHOICES

    county_name = models.CharField(max_length=255, unique=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='NO_CRITERIA',
    )
    deals_with_council_tax = models.BooleanField(
        default=False,
        help_text='Most county councils delegate council tax collection to their districts.',
    )
    min_dividend_pence = models.IntegerField(blank=True, null=True)
    blocked_reason = models.TextField(blank=True, default='')
    contact_name = models.CharField(max_length=255, blank=True, default='')
    contact_number = models.CharField(max_length=255, blank=True, default='')
    last_reviewed = models.DateField(blank=True, null=True)

    class Meta:
        verbose_name = 'County Council'
        verbose_name_plural = 'County Councils'
        ordering = ['county_name']

    def __str__(self):
        return self.county_name


class CreditorVoteSummary(models.Model):
    # Choices for latest_vote_outcome
    VOTE_OUTCOME_CHOICES = [
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('modified', 'Modified'),
        ('pod', 'POD'),
    ]

    # Links to each of the three creditor types - exactly one should be set
    creditor_criteria = models.ForeignKey(
        CreditorCriteria,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='vote_summaries'
    )
    council_rule = models.ForeignKey(
        CouncilRule,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='vote_summaries'
    )
    county_council = models.ForeignKey(
        CountyCouncil,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='vote_summaries'
    )

    total_votes = models.IntegerField(default=0)
    rejected_count = models.IntegerField(null=True, blank=True)
    accepted_count = models.IntegerField(null=True, blank=True)
    modified_count = models.IntegerField(null=True, blank=True)
    pod_count = models.IntegerField(null=True, blank=True)
    latest_vote_date = models.DateField(null=True, blank=True)
    latest_vote_outcome = models.CharField(
        max_length=20,
        choices=VOTE_OUTCOME_CHOICES,
        null=True,
        blank=True
    )
    crm_rows_covered = models.IntegerField(default=0)
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Creditor Vote Summaries"
        constraints = [
            models.CheckConstraint(
                condition=(
                    (models.Q(creditor_criteria__isnull=False) & models.Q(council_rule__isnull=True) & models.Q(county_council__isnull=True)) |
                    (models.Q(creditor_criteria__isnull=True) & models.Q(council_rule__isnull=False) & models.Q(county_council__isnull=True)) |
                    (models.Q(creditor_criteria__isnull=True) & models.Q(council_rule__isnull=True) & models.Q(county_council__isnull=False))
                ),
                name='exactly_one_creditor_type_set'
            )
        ]

    def __str__(self):
        if self.creditor_criteria:
            return f"Vote Summary: {self.creditor_criteria.creditor_name}"
        elif self.council_rule:
            return f"Vote Summary: {self.council_rule.council_name}"
        elif self.county_council:
            return f"Vote Summary: {self.county_council.county_name}"
        return "Vote Summary (unlinked)"


class CrmSyncRun(models.Model):
    STATUS_CHOICES = [('RUNNING', 'Running'), ('SUCCESS', 'Success'), ('FAILED', 'Failed')]
    TRIGGER_CHOICES = [('MANUAL', 'Manual'), ('SCHEDULED', 'Scheduled/Cron'), ('CLI', 'CLI')]

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='RUNNING')
    stage = models.CharField(max_length=100, blank=True, default='')
    trigger_source = models.CharField(max_length=10, choices=TRIGGER_CHOICES, default='CLI')
    triggered_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='crm_sync_runs')
    dry_run = models.BooleanField(default=False)
    crm_rows_fetched = models.IntegerField(null=True, blank=True)
    records_created = models.IntegerField(default=0)
    records_updated = models.IntegerField(default=0)
    creditor_criteria_count = models.IntegerField(default=0)
    council_rule_count = models.IntegerField(default=0)
    county_council_count = models.IntegerField(default=0)
    error_message = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"CrmSyncRun {self.id} ({self.status}) {self.started_at}"


class CreditorVoteChangeEvent(models.Model):
    vote_summary = models.ForeignKey(CreditorVoteSummary, on_delete=models.CASCADE)
    sync_run = models.ForeignKey(CrmSyncRun, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=CreditorVoteSummary.VOTE_OUTCOME_CHOICES)
    detected_at = models.DateTimeField(auto_now_add=True)


class CreditorMocAlert(models.Model):
    vote_summary = models.ForeignKey(CreditorVoteSummary, on_delete=models.CASCADE)
    alert_date = models.DateField()
    triggered_by_status = models.CharField(
        max_length=20,
        choices=CreditorVoteSummary.VOTE_OUTCOME_CHOICES,
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    emailed = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['vote_summary', 'alert_date'],
                name='unique_moc_alert_per_creditor_per_day'
            )
        ]

    def __str__(self):
        return f"MOC Alert for vote_summary={self.vote_summary_id} on {self.alert_date}"


class CreditorNonAcceptMilestone(models.Model):
    vote_summary = models.ForeignKey(CreditorVoteSummary, on_delete=models.CASCADE)
    milestone_date = models.DateField()
    status = models.CharField(max_length=20, choices=CreditorVoteSummary.VOTE_OUTCOME_CHOICES)
    first_event_at = models.DateTimeField()
    third_event_at = models.DateTimeField()
    count = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    emailed = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["vote_summary", "milestone_date", "status"],
                name="uniq_nonaccept_milestone_per_day_status"
            )
        ]

    def __str__(self):
        return f"Non-Accept Milestone ({self.status}) for vote_summary={self.vote_summary_id} on {self.milestone_date}"


class MocDigestLog(models.Model):
    """
    One row per calendar day the send_moc_daily_digest command actually sent
    an email. Guarantees the digest goes out at most once per day even if the
    scheduler double-fires or someone re-runs the command by hand - unlike the
    per-row `emailed` flags (which only stop re-sending alerts/milestones that
    already exist), this also blocks a duplicate send on a day with zero new
    alerts but where the report itself would otherwise resend the same totals.
    """
    date = models.DateField(unique=True)
    sent_at = models.DateTimeField(auto_now_add=True)
    recipients = models.TextField(blank=True, default='')
    alerts_count = models.IntegerField(default=0)
    milestones_count = models.IntegerField(default=0)
    vote_changes_total = models.IntegerField(default=0)

    def __str__(self):
        return f"MOC digest sent for {self.date} at {self.sent_at}"


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
    county = models.ForeignKey(
        CountyCouncil,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='districts',
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


class GuidelineCategory(models.Model):
    """Top-level grouping for SFS expenditure guideline rows."""

    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=100)
    upper_cap = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'guideline_categories'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class ExpenditureGuideline(models.Model):
    """SFS expenditure guideline amounts per household composition."""

    id = models.BigAutoField(primary_key=True)
    category_group = models.ForeignKey(
        GuidelineCategory,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='guidelines',
    )
    category = models.CharField(max_length=100, unique=True, db_index=True)
    label = models.CharField(max_length=255)
    max = models.BooleanField(default=False)
    min = models.BooleanField(default=False)
    sort_order = models.IntegerField(default=0)

    # Single-adult and dual-adult (no children)
    adult_1 = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    adult_2 = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Single adult + children
    adult_1_child_1 = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    adult_1_child_2 = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    adult_1_child_3 = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    adult_1_child_4 = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    adult_1_child_5 = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Two adults + children
    adult_2_child_1 = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    adult_2_child_2 = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    adult_2_child_3 = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    adult_2_child_4 = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    adult_2_child_5 = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Per-unit rates
    per_child = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    per_vehicle = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    first_adult = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    additional_adult = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    child_under_16 = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    child_16_18 = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Representative-specific rates
    watch_per_adult = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    non_watch_per_adult = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    watch_per_vehicle = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    non_watch_per_vehicle = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Household caps
    one_adult_cap = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    two_adults_cap = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    formula = models.TextField(blank=True)
    below_action = models.CharField(max_length=50, blank=True)
    above_action = models.CharField(max_length=50, blank=True)
    mismatch_action = models.CharField(max_length=50, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'expenditure_guidelines'
        ordering = ['category_group__sort_order', 'sort_order', 'category']

    def __str__(self):
        return f"{self.label} ({self.category})"


# extracted_data JSON schema:
# {
#   "agency": "Experian",
#   "client_name": "John Smith",
#   "report_date": "2024-01-15",
#   "accounts": [
#     {
#       "raw_name": "BARCLAYCARD",
#       "normalised_name": "barclaycard",
#       "matched_creditor": "Barclaycard",
#       "account_age_months": 34,
#       "missed_payments_last_3_months": 1,
#       "recent_spending": true,
#       "current_balance": 230000,       # pence
#       "credit_limit": 300000,          # pence
#       "utilisation_pct": 76.7,
#       "account_status": "open",        # open|closed|defaulted|arrangement
#       "payment_history_months": 24
#     }
#   ],
#   "unmatched_accounts": ["RAW NAME THAT DID NOT MAP"]
# }

EXTRACTION_STATUS_CHOICES = [
    ("pending", "Pending"),
    ("extracted", "Extracted"),
    ("failed", "Failed"),
]


class CreditReport(models.Model):
    id = models.BigAutoField(primary_key=True)
    aryza_reference = models.CharField(
        max_length=255, db_index=True,
        help_text="Aryza case reference this report belongs to"
    )
    uploaded_file = models.FileField(
        upload_to="credit_reports/%Y/%m/",
        help_text="Raw PDF file"
    )
    agency = models.CharField(
        max_length=100, blank=True, default="",
        help_text="Detected credit agency: Experian, Equifax, TransUnion, Unknown"
    )
    client_name_on_report = models.CharField(
        max_length=255, blank=True, default="",
        help_text="Client name as it appears on the credit report"
    )
    extraction_status = models.CharField(
        max_length=20,
        choices=EXTRACTION_STATUS_CHOICES,
        default="pending"
    )
    extracted_data = models.JSONField(
        null=True, blank=True,
        help_text="Structured per-creditor data extracted from PDF"
    )
    extraction_error = models.TextField(
        blank=True, default="",
        help_text="Error message if extraction failed"
    )
    uploaded_by = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="uploaded_credit_reports"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["aryza_reference"])]

    def __str__(self):
        return f"CreditReport({self.aryza_reference}, {self.extraction_status})"


# ---------------------------------------------------------------------------
# Department & rule-visibility models
# ---------------------------------------------------------------------------

class Department(models.Model):
    """Organisational department used to control rule visibility per team."""

    name = models.CharField(max_length=255, unique=True)
    slug = models.SlugField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Department'
        verbose_name_plural = 'Departments'
        ordering = ['name']

    def __str__(self):
        return self.name


class UserProfile(models.Model):
    """Extended profile for Django's built-in User — links user to a Department."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='members',
    )

    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f"Profile({self.user.username})"


class DepartmentRuleVisibility(models.Model):
    """Controls whether a Department can see a particular GlobalCriteria rule."""

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='rule_visibilities',
    )
    rule_key = models.ForeignKey(
        GlobalCriteria,
        on_delete=models.CASCADE,
        to_field='rule_key',
        related_name='department_visibilities',
    )
    is_visible = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Department Rule Visibility'
        verbose_name_plural = 'Department Rule Visibilities'
        unique_together = [('department', 'rule_key')]

    def __str__(self):
        return f"{self.department} — {self.rule_key_id}: {self.is_visible}"


class DepartmentCreditorVisibility(models.Model):
    """Controls whether a Department can see a particular CreditorCriteria entry."""

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='creditor_visibilities',
    )
    creditor = models.ForeignKey(
        CreditorCriteria,
        on_delete=models.CASCADE,
        related_name='department_visibilities',
    )
    is_visible = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Department Creditor Visibility'
        verbose_name_plural = 'Department Creditor Visibilities'
        unique_together = [('department', 'creditor')]

    def __str__(self):
        return f"{self.department} — {self.creditor}: {self.is_visible}"


class DepartmentCouncilVisibility(models.Model):
    """Controls whether a Department can see a particular CouncilRule."""

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='council_visibilities',
    )
    council = models.ForeignKey(
        CouncilRule,
        on_delete=models.CASCADE,
        related_name='department_visibilities',
    )
    is_visible = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Department Council Visibility'
        verbose_name_plural = 'Department Council Visibilities'
        unique_together = [('department', 'council')]

    def __str__(self):
        return f"{self.department} — {self.council}: {self.is_visible}"


class DepartmentSFSVisibility(models.Model):
    """Controls whether a Department can see a particular ExpenditureGuideline."""

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='sfs_visibilities',
    )
    guideline = models.ForeignKey(
        ExpenditureGuideline,
        on_delete=models.CASCADE,
        related_name='department_visibilities',
    )
    is_visible = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Department SFS Visibility'
        verbose_name_plural = 'Department SFS Visibilities'
        unique_together = [('department', 'guideline')]
        ordering = ['department', 'guideline']

    def __str__(self):
        return f"{self.department} — {self.guideline}: {self.is_visible}"


class DepartmentFeatureAccess(models.Model):
    """Controls which application features a Department's users can access."""

    FEATURE_KEY_CHOICES = [
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
    ]

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='feature_accesses',
    )
    feature_key = models.CharField(max_length=50, choices=FEATURE_KEY_CHOICES)
    is_enabled = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Department Feature Access'
        verbose_name_plural = 'Department Feature Accesses'
        unique_together = [('department', 'feature_key')]

    def __str__(self):
        return f"{self.department} — {self.feature_key}: {self.is_enabled}"


class DepartmentFeaturePermission(models.Model):
    """
    Controls read/write permission levels for departments per feature.
    
    For rule management and SFS features, departments can have:
    - READ: View-only access
    - WRITE: Full access including edit, delete, add operations
    
    Features: General Creditors, Rep Creditors, Global Rules, Councils, Dividends, SFS
    """

    PERMISSION_LEVEL_CHOICES = [
        ('READ', 'Read Only'),
        ('WRITE', 'Read & Write'),
    ]

    FEATURES_WITH_PERMISSIONS = [
        ('general_creditors', 'General Creditors'),
        ('representative_creditors', 'Representative Creditors'),
        ('global_rules', 'Global Rules'),
        ('councils', 'Councils'),
        ('dividends', 'Dividends'),
        ('sfs_guidelines', 'SFS Guidelines'),
    ]

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='feature_permissions',
    )
    feature_key = models.CharField(
        max_length=50,
        choices=FEATURES_WITH_PERMISSIONS,
        help_text="Feature to which this permission applies"
    )
    permission_level = models.CharField(
        max_length=10,
        choices=PERMISSION_LEVEL_CHOICES,
        default='READ',
        help_text="READ: View-only, WRITE: Full access (edit, delete, add)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Department Feature Permission'
        verbose_name_plural = 'Department Feature Permissions'
        unique_together = [('department', 'feature_key')]
        ordering = ['department', 'feature_key']

    def __str__(self):
        return f"{self.department} — {self.feature_key}: {self.permission_level}"

    def has_write_permission(self):
        """Check if this department has write access for this feature."""
        return self.permission_level == 'WRITE'

    def has_read_permission(self):
        """Check if this department has read access for this feature."""
        return self.permission_level in ['READ', 'WRITE']
