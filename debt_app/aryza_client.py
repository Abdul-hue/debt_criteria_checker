"""
Aryza Database Client for Django Application

READ-ONLY client for querying the Aryza MySQL database connected as 'aryza' in Django settings.
Handles client lookup, income, creditors, property, vehicles, and flags.
"""

import logging
import re
from typing import Dict, List, Optional, Any
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.db import connections
from django.db.utils import OperationalError

logger = logging.getLogger(__name__)


# ============================================================================
# MODULE-LEVEL SCHEMA-ABSENT WARNINGS (fired once at import time)
# ============================================================================

_SCHEMA_ABSENT_WARNED = False


def _warn_schema_absent_once():
    global _SCHEMA_ABSENT_WARNED
    if not _SCHEMA_ABSENT_WARNED:
        _SCHEMA_ABSENT_WARNED = True
        logger.warning(
            "iva_client schema: iva_bankruptcy_dividend and iva_bankruptcy_return "
            "are absent from this Aryza instance — WATCH-22.3 and TIG-15.5 will "
            "evaluate as not-applicable."
        )
        logger.warning("aryza schema: client_open_banking_transactions absent — open_banking_transactions defaults to []")
        logger.warning("aryza schema: factfind_vulnerability absent — vulnerability_flags defaults to {}")
        logger.warning("aryza schema: factfind_hmrc_details absent — hmrc_details defaults to None")
        logger.warning("aryza schema: client_flags absent — client_flags defaults to {}")
        logger.warning("aryza schema: factfind_transfers absent — transfers defaults to []")
        logger.warning("aryza schema: factfind_additional_flags absent — additional_flags defaults to {}")


_warn_schema_absent_once()


# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================

class AryzaConnectionError(Exception):
    """Raised when unable to connect to Aryza database."""
    pass


class AryaTimeoutError(Exception):
    """Raised when Aryza database query times out."""
    pass


class AryzaCaseNotFoundError(Exception):
    """Raised when client reference not found in Aryza database."""
    pass


class AryzaDataError(Exception):
    """Raised when data retrieval fails after successful connection."""
    pass


# ============================================================================
# TIMEOUT HANDLING
# ============================================================================

_TIMEOUT_PATTERN = re.compile(r"timeout|timed out|connect_timeout|lost connection|server has gone away", re.I)


def _is_timeout_error(exc: Exception) -> bool:
    """Check if exception is a timeout-related error."""
    return bool(_TIMEOUT_PATTERN.search(str(exc)))


def _handle_operational_error(exc: Exception) -> None:
    """Handle database operational errors with appropriate exception mapping."""
    if _is_timeout_error(exc):
        raise AryaTimeoutError(str(exc)) from exc
    raise AryzaConnectionError(str(exc)) from exc


# Normalise raw Aryza employment_status values to the keys the criteria engine expects.
_INCOME_SOURCE_MAP = {
    "benefits_only": "benefits",
    "universal_credit": "uc",
}


# ============================================================================
# TYPE DEFINITIONS
# ============================================================================

class CaseData:
    """Data transfer object for case information from Aryza."""
    
    def __init__(self):
        self.aryza_reference: str = ""
        self.clientid: int = 0
        self.client_name: str = ""
        self.dob: Optional[str] = None
        self.employment_status: str = "unemployed"
        self.total_unsecured_debt: int = 0
        self.disposable_income: int = 0
        self.creditors: List[Dict[str, Any]] = []
        self.income: Dict[str, int] = {
            "employment": 0,
            "universal_credit": 0,
            "dla": 0,
            "pip": 0,
            "other_benefits": 0,
            "third_party_contribution": 0,
            "total": 0,
        }
        self.expenditure: Dict[str, int] = {
            "disability_expenses": 0,
            "total": 0,
        }
        self.sfs_expenditure_breakdown: List[Dict[str, Any]] = []
        self.gold_transactions: List[Dict[str, Any]] = []
        self.property: Dict[str, Any] = {
            "owns_property": False,
            "property_value": None,
            "mortgage_balance": None,
            "equity": None,
        }
        self.vehicle: Dict[str, Any] = {
            "has_vehicle": False,
            "vehicle_value": None,
            "vehicle_make": None,
            "hp_monthly_payment": None,
            "car_finance_start_date": None,
        }
        self.flags: Dict[str, Any] = {
            "previous_iva": False,
            "previous_iva_failed_reason": None,
            "gambling_present": False,
            "antecedent_transactions": False,
            "vulnerability_claimed": False,
            "has_third_party": False,
        }
        self.dependants: List[Dict[str, int]] = []
        self.audit_log: List[Dict[str, Any]] = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "aryza_reference": self.aryza_reference,
            "clientid": self.clientid,
            "client_name": self.client_name,
            "dob": self.dob,
            "employment_status": self.employment_status,
            "total_unsecured_debt": self.total_unsecured_debt,
            "disposable_income": self.disposable_income,
            "creditors": self.creditors,
            "income": self.income,
            "expenditure": self.expenditure,
            "sfs_expenditure_breakdown": self.sfs_expenditure_breakdown,
            "gold_transactions": self.gold_transactions,
            "property": self.property,
            "vehicle": self.vehicle,
            "flags": self.flags,
            "dependants": self.dependants,
            "audit_log": self.audit_log,
        }


# ============================================================================
# ARYZA CLIENT
# ============================================================================

class AryzaClient:
    """Client for querying read-only Aryza database."""
    
    def __init__(self):
        self.db_alias = "aryza"
    
    def _audit(self, case: CaseData, table: str, status: str, details: str = "") -> None:
        """Record an audit entry for a data fetch attempt."""
        entry = {
            "table": table,
            "status": status,
            "details": details,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        case.audit_log.append(entry)
        
        # Log to standard logger as well
        log_msg = f"DATA AUDIT: Table '{table}' -> {status}"
        if details:
            log_msg += f" ({details})"
        
        if status == "FOUND":
            logger.info(log_msg)
        elif status in ("EMPTY", "SCHEMA-ABSENT"):
            logger.warning(log_msg)
        else:
            logger.error(log_msg)

    def _get_connection(self):
        """Get database connection with error handling."""
        if self.db_alias not in settings.DATABASES:
            raise AryzaConnectionError(f"Aryza database '{self.db_alias}' is not configured in settings.DATABASES")
        
        try:
            connection = connections[self.db_alias]
            # Test the connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            return connection
        except OperationalError as e:
            logger.error(f"Failed to connect to Aryza database: {e}")
            _handle_operational_error(e)
        except Exception as e:
            # Misconfigured settings (e.g. HOST/USER/PASSWORD unset) can raise
            # driver-level errors (AttributeError, TypeError, etc.) before Django
            # wraps them as OperationalError. Surface these as AryzaConnectionError
            # too, so callers get a clean 503 instead of an unhandled 500.
            logger.error(f"Failed to connect to Aryza database: {e}")
            raise AryzaConnectionError(str(e)) from e
    
    def fetch_case_by_reference(self, reference: str) -> CaseData:
        """
        Fetch complete case data by client reference.
        
        Args:
            reference: Client reference number (can be string or numeric)
        
        Returns:
            CaseData object with all client financial information
        
        Raises:
            AryzaCaseNotFoundError: If client not found
            AryzaConnectionError: If database connection fails
            AryzaDataError: If data retrieval fails
        """
        connection = self._get_connection()
        
        # Step 1: Find the client
        clientid = self._find_client_id(connection, reference)
        if clientid is None:
            raise AryzaCaseNotFoundError(f"No client found for reference: {reference}")
        
        # Step 2: Build case data
        case = CaseData()
        case.aryza_reference = reference
        case.clientid = clientid
        
        try:
            # Fetch core client data
            self._fetch_client_data(connection, case, clientid)
            
            # Fetch income data
            self._fetch_income_data(connection, case, clientid)
            
            # Fetch detailed expenditure (SFS breakdown)
            self._fetch_expenditure_data(connection, case, clientid)
            
            # Fetch transactions (Open Banking)
            self._fetch_transaction_data(connection, case, clientid)
            
            # Fetch creditor data
            self._fetch_creditor_data(connection, case, clientid)
            
            # Fetch debt arrangements
            self._fetch_debt_arrangements(connection, case, clientid)
            
            # Fetch property
            self._fetch_property_data(connection, case, clientid)
            
            # Fetch vehicle
            self._fetch_vehicle_data(connection, case, clientid)
            
            # Fetch flags
            self._fetch_flags_data(connection, case, clientid)
            
            # Calculate totals
            self._calculate_totals(case)
            
            return case
        
        except (AryzaConnectionError, AryzaCaseNotFoundError):
            raise
        except OperationalError as e:
            _handle_operational_error(e)
        except Exception as e:
            logger.error(f"Error fetching case data for clientid {clientid}: {e}")
            raise AryzaDataError(f"Failed to fetch case data: {e}")
    
    # ========================================================================
    # HELPER METHODS - CLIENT LOOKUP
    # ========================================================================
    
    def _find_client_id(self, connection, reference: str) -> Optional[int]:
        """Find clientid by variety of reference columns."""
        queries = [
            ("SELECT id FROM client WHERE alt_ref = %s", reference),
            ("SELECT id FROM client WHERE import_reference = %s", reference),
            ("SELECT clientid FROM td_client WHERE td_case_code = %s", reference),
            ("SELECT clientid FROM iva_client WHERE payment_ref = %s", reference),
        ]
        
        # If reference is numeric, also try as ID
        if reference.isdigit():
            ref_int = int(reference)
            queries.insert(0, ("SELECT id FROM client WHERE id = %s", ref_int))
            queries.append(("SELECT clientid FROM td_client WHERE clientid = %s", ref_int))
            queries.append(("SELECT clientid FROM iva_client WHERE clientid = %s", ref_int))
        
        with connection.cursor() as cursor:
            for query, param in queries:
                try:
                    cursor.execute(query, [param])
                    row = cursor.fetchone()
                    if row:
                        return row[0]
                except Exception as e:
                    logger.debug(f"Query failed ({query}): {e}")
                    continue
        
        return None
    
    # ========================================================================
    # HELPER METHODS - DATA FETCHING
    # ========================================================================
    
    def _fetch_client_data(self, connection, case: CaseData, clientid: int) -> None:
        """Fetch core client data from client table."""
        with connection.cursor() as cursor:
            # Get client name from client table
            try:
                cursor.execute(
                    "SELECT id, firstname, lastname, dob FROM client WHERE id = %s LIMIT 1",
                    [clientid]
                )
                client_row = cursor.fetchone()
                if client_row:
                    fname = client_row[1] or ""
                    lname = client_row[2] or ""
                    case.client_name = f"{fname} {lname}".strip() or f"Client {clientid}"
                    
                    # Convert dob (Unix timestamp) to ISO date string
                    if client_row[3]:
                        try:
                            case.dob = datetime.fromtimestamp(int(client_row[3])).date().isoformat()
                        except (ValueError, TypeError, OverflowError):
                            case.dob = None
                    self._audit(case, "client", "FOUND", f"Name: {case.client_name}")
                else:
                    case.client_name = f"Client {clientid}"
                    self._audit(case, "client", "EMPTY", "No row found in client table")
            except Exception as e:
                logger.warning(f"Failed to fetch client name for clientid {clientid}: {e}")
                case.client_name = f"Client {clientid}"
                self._audit(case, "client", "ERROR", str(e))
            
            # Fetch dependants / children ages
            try:
                # 1. Primary: factfind_dependants (absent in this Aryza instance — isolated)
                try:
                    cursor.execute(
                        "SELECT ages_of_children FROM factfind_dependants WHERE clientid = %s LIMIT 1",
                        [clientid]
                    )
                    dep_row = cursor.fetchone()
                    if dep_row and dep_row[0]:
                        self._parse_children_ages(case, dep_row[0])
                        self._audit(case, "factfind_dependants", "FOUND", f"Ages: {dep_row[0]}")
                except Exception:
                    pass  # table absent — fall through to client_dependant
                
                # 2. Fallback: client_dependant — no age column; calculate from dob (unix ts)
                if not case.dependants:
                    try:
                        cursor.execute(
                            "SELECT dob FROM client_dependant "
                            "WHERE clientid = %s AND deleted = 0 AND dependant = 1",
                            [clientid]
                        )
                        rows = cursor.fetchall()
                        if rows:
                            today = datetime.now().date()
                            for row in rows:
                                if row[0] is not None:
                                    try:
                                        born = datetime.fromtimestamp(int(row[0])).date()
                                        age = (today.year - born.year
                                               - ((today.month, today.day) < (born.month, born.day)))
                                        if 0 <= age <= 120:
                                            case.dependants.append({"age": age})
                                    except (ValueError, TypeError, OverflowError):
                                        pass
                            if case.dependants:
                                self._audit(case, "client_dependant", "FOUND",
                                            f"Fetched {len(case.dependants)} dependants (age from dob)")
                            else:
                                self._audit(case, "client_dependant", "EMPTY",
                                            "Rows found but no valid ages from dob")
                        else:
                            self._audit(case, "client_dependant", "EMPTY", "No dependant rows found")
                    except Exception as e:
                        self._audit(case, "client_dependant", "ERROR", str(e))
                
                # 3. Fallback: dependants (another common table name)
                if not case.dependants:
                    try:
                        cursor.execute(
                            "SELECT age FROM dependants WHERE clientid = %s",
                            [clientid]
                        )
                        rows = cursor.fetchall()
                        if rows:
                            for row in rows:
                                if row[0] is not None:
                                    case.dependants.append({"age": int(row[0])})
                            self._audit(case, "dependants", "FOUND", f"Fetched {len(rows)} dependants")
                    except Exception:
                        pass

                if not case.dependants:
                    self._audit(case, "dependants_check", "EMPTY", "No dependants found in any table")
            except Exception as e:
                logger.debug(f"Dependants fetch error for clientid {clientid}: {e}")
                self._audit(case, "dependants_check", "ERROR", str(e))

            # Try td_client for summary totals (may be empty in TIG)
            try:
                cursor.execute(
                    "SELECT td_total_debt, td_contribution, td_third_party_contribution, "
                    "       td_no_cars, td_third_party_contributor "
                    "FROM td_client WHERE clientid = %s",
                    [clientid]
                )
                td_row = cursor.fetchone()
                if td_row:
                    if td_row[0] is not None:
                        case.total_unsecured_debt = self._pence(td_row[0])
                    if td_row[1] is not None:
                        case.disposable_income = self._pence(td_row[1])
                    if td_row[2] is not None:
                        case.income["third_party_contribution"] = self._pence(td_row[2])
                    case.vehicle["has_vehicle"] = bool(td_row[3] and td_row[3] > 0)
                    case.flags["has_third_party"] = bool(td_row[4])
                    self._audit(case, "td_client", "FOUND", "Core financial summary loaded")
                else:
                    self._audit(case, "td_client", "EMPTY", "No row in td_client")
            except Exception as e:
                logger.debug(f"td_client not available for clientid {clientid}: {e}")
                self._audit(case, "td_client", "ERROR", str(e))

            # Try client_iande for the I&E statement DI.
            # td_client.td_contribution is the IVA proposal contribution and can be
            # negative (expenses > income) or zero before a proposal is drafted.
            # When that happens, fall back to the I&E statement's own DI figure,
            # which matches what Case Assessment reads from the Aryza CRM API.
            if case.disposable_income <= 0:
                try:
                    cursor.execute(
                        "SELECT di FROM client_iande "
                        "WHERE clientid = %s ORDER BY id DESC LIMIT 1",
                        [clientid]
                    )
                    iande_row = cursor.fetchone()
                    if iande_row and iande_row[0] is not None:
                        iande_di = self._pence(iande_row[0])
                        if iande_di > 0:
                            case.disposable_income = iande_di
                            self._audit(case, "client_iande", "FOUND",
                                        f"DI fallback: £{iande_di/100.0:.2f}")
                        else:
                            self._audit(case, "client_iande", "FOUND", "DI non-positive, skipped")
                    else:
                        self._audit(case, "client_iande", "EMPTY", "No iande row found")
                except Exception as e:
                    # Table absent or column missing in this Aryza instance — safe to ignore.
                    self._audit(case, "client_iande", "SCHEMA-ABSENT", str(e))

            # Try iva_client for TPC fallback only — iva_bankruptcy_dividend and
            # iva_bankruptcy_return are absent from this Aryza instance (schema-absent).
            bankruptcy_dividend = None  # schema-absent: column not in this Aryza instance
            bankruptcy_return = None    # schema-absent: column not in this Aryza instance
            try:
                cursor.execute(
                    "SELECT iva_third_party_contribution "
                    "FROM iva_client WHERE clientid = %s",
                    [clientid]
                )
                iva_row = cursor.fetchone()
                if iva_row:
                    if case.income.get("third_party_contribution") == 0 and iva_row[0] is not None:
                        case.income["third_party_contribution"] = self._pence(iva_row[0])
                        self._audit(case, "iva_client", "FOUND", "TPC fallback found")
                    else:
                        self._audit(case, "iva_client", "FOUND", "Row present, TPC already set or null")
                else:
                    self._audit(case, "iva_client", "EMPTY", "No row in iva_client")
            except Exception as e:
                logger.debug(f"iva_client fetch failed for {clientid}: {e}")
                self._audit(case, "iva_client", "ERROR", str(e))
    
    def _fetch_income_data(self, connection, case: CaseData, clientid: int) -> None:
        """Fetch income data from client_income table (wide-column format)."""
        with connection.cursor() as cursor:
            try:
                cursor.execute(
                    """SELECT
                        earnings_net, earnings_net_frequency,
                        earnings_partner_net, earnings_partner_net_frequency,
                        benefit_universal_credit, benefit_universal_credit_frequency,
                        benefit_dla, benefit_dla_frequency,
                        benefit_pip, benefit_pip_frequency,
                        benefit_child, benefit_housing, benefit_income_support,
                        benefit_working_tax_credit, benefit_child_tax_credit,
                        benefit_esa, benefit_carers_allowance,
                        benefit_aa, benefit_bereavement, benefit_incapacity,
                        benefit_industrial_disablement, benefit_job_seekers_allowance,
                        benefit_job_seekers_allowance_cont_based,
                        benefit_maternity_allowance, benefit_statutory_maternity_pay,
                        benefit_statutory_sick_pay, benefit_council_tax,
                        pension_state, pension_client, pension_private,
                        pension_credit, pension_other,
                        student_loan, student_grant, child_income_support,
                        non_dependant_contributions, lodger_income
                    FROM client_income WHERE clientid = %s LIMIT 1""",
                    [clientid]
                )
                row = cursor.fetchone()
                if row:
                    # col indices after adding earnings_partner_net_frequency at [3]:
                    # [0] earnings_net  [1] earnings_net_frequency
                    # [2] earnings_partner_net  [3] earnings_partner_net_frequency
                    # [4] uc  [5] uc_freq  [6] dla  [7] dla_freq  [8] pip  [9] pip_freq
                    # [10:17] other means-tested benefits (child..carers)
                    # [17:27] additional benefits (aa..council_tax)
                    # [27:32] pensions (state, client, private, credit, other)
                    # [32:35] student_loan, student_grant, child_income_support
                    # [35] non_dependant_contributions  [36] lodger_income

                    # Employment income (normalise to monthly, both client and partner)
                    emp_net = self._pence(row[0])
                    emp_freq = row[1] or 'monthly'
                    emp_partner = self._pence(row[2])
                    emp_partner_freq = row[3] or 'monthly'
                    case.income["employment"] = (
                        self._normalise_to_monthly(emp_net, emp_freq) +
                        self._normalise_to_monthly(emp_partner, emp_partner_freq)
                    )

                    # Universal Credit
                    uc_amt = self._pence(row[4])
                    uc_freq = row[5] or 'monthly'
                    case.income["universal_credit"] = self._normalise_to_monthly(uc_amt, uc_freq)

                    # DLA
                    dla_amt = self._pence(row[6])
                    dla_freq = row[7] or 'monthly'
                    case.income["dla"] = self._normalise_to_monthly(dla_amt, dla_freq)

                    # PIP
                    pip_amt = self._pence(row[8])
                    pip_freq = row[9] or 'monthly'
                    case.income["pip"] = self._normalise_to_monthly(pip_amt, pip_freq)

                    # Other means-tested benefits and additional benefit types
                    # (child, housing, income support, tax credits, ESA, carer, AA,
                    # bereavement, incapacity, industrial disablement, JSA x2,
                    # maternity allowance, statutory maternity/sick pay, council tax)
                    other = sum(self._pence(v) for v in row[10:27] if v is not None)
                    case.income["other_benefits"] = other

                    # Pension income (state, client, private, credit, other)
                    pension = sum(self._pence(v) for v in row[27:32] if v is not None)
                    case.income["other_benefits"] += pension

                    # Other income (student loan, student grant, child income support)
                    other_income = sum(self._pence(v) for v in row[32:35] if v is not None)
                    case.income["other_benefits"] += other_income

                    # Third-party contributions (non-dependant, lodger)
                    tp = sum(self._pence(v) for v in [row[35], row[36]] if v is not None)
                    if tp > 0 and case.income["third_party_contribution"] == 0:
                        case.income["third_party_contribution"] = tp

                    # Determine employment status — detect UC as a distinct source
                    if case.income["employment"] > 0:
                        case.employment_status = "employed"
                    elif case.income["universal_credit"] > 0:
                        case.employment_status = "universal_credit"
                    elif case.income["dla"] + case.income["pip"] + case.income["other_benefits"] > 0:
                        case.employment_status = "benefits_only"
                    case.employment_status = _INCOME_SOURCE_MAP.get(
                        case.employment_status, case.employment_status
                    )

                    logger.debug(f"Income fetched for {clientid}: emp={case.income['employment']}, uc={case.income['universal_credit']}")
                    self._audit(case, "client_income", "FOUND", f"Total: £{case.income['total']/100.0:.2f}")
                else:
                    self._audit(case, "client_income", "EMPTY", "No income record found")
            except Exception as e:
                logger.debug(f"Failed to fetch client_income for clientid {clientid}: {e}")
                self._audit(case, "client_income", "ERROR", str(e))
            
            # Fallback: try client_expenses for income type entries (latest statement only)
            try:
                cursor.execute(
                    "SELECT MAX(statement_id) FROM client_expenses "
                    "WHERE clientid = %s AND type = 'income' AND statement_id IS NOT NULL",
                    [clientid]
                )
                max_stmt = cursor.fetchone()[0]
                if max_stmt is not None:
                    cursor.execute(
                        "SELECT field, value, frequency FROM client_expenses "
                        "WHERE clientid = %s AND type = 'income' AND statement_id = %s",
                        [clientid, max_stmt]
                    )
                else:
                    cursor.execute(
                        "SELECT field, value, frequency FROM client_expenses "
                        "WHERE clientid = %s AND type = 'income'",
                        [clientid]
                    )
                rows = cursor.fetchall()
                if rows:
                    _se_income = 0
                    _cis_income = 0
                    for row in rows:
                        field, value, freq = row[0], self._pence(row[1]), row[2] or 'monthly'
                        monthly_val = self._normalise_to_monthly(value, freq)
                        _fl = field.lower()
                        if 'self_employed' in _fl or 'self-employed' in _fl:
                            _se_income += monthly_val
                            case.income["employment"] += monthly_val
                        elif 'cis' in _fl:
                            _cis_income += monthly_val
                            case.income["employment"] += monthly_val
                        elif 'earnings' in _fl or 'employment' in _fl:
                            case.income["employment"] += monthly_val
                        elif 'universal_credit' in _fl:
                            case.income["universal_credit"] += monthly_val
                        elif 'dla' in _fl:
                            case.income["dla"] += monthly_val
                        elif 'pip' in _fl:
                            case.income["pip"] += monthly_val
                        else:
                            case.income["other_benefits"] += monthly_val
                    # Self-employed/CIS take priority over whatever client_income set
                    if _cis_income > 0:
                        case.employment_status = "cis"
                    elif _se_income > 0:
                        case.employment_status = "self_employed"
                    self._audit(case, "client_expenses (income)", "FOUND", f"Fetched {len(rows)} items")
                else:
                    self._audit(case, "client_expenses (income)", "EMPTY", "No income entries in expenses table")
            except Exception as e:
                logger.debug(f"Failed to fetch client_expenses income fallback for clientid {clientid}: {e}")
                self._audit(case, "client_expenses (income)", "ERROR", str(e))

    def _fetch_expenditure_data(self, connection, case: CaseData, clientid: int) -> None:
        """Fetch detailed expenditure data from client_expenses for SFS breakdown."""
        with connection.cursor() as cursor:
            try:
                # Fetch non-income expenses from the latest SFS statement only.
                # Aryza creates a new statement_id on each SFS revision, leaving the
                # old rows in place. Without this filter, every expense is counted
                # once per revision, doubling (or more) the expenditure total.
                cursor.execute(
                    "SELECT MAX(statement_id) FROM client_expenses "
                    "WHERE clientid = %s AND type != 'income' AND statement_id IS NOT NULL",
                    [clientid]
                )
                max_stmt = cursor.fetchone()[0]
                if max_stmt is not None:
                    cursor.execute(
                        "SELECT field, value, frequency FROM client_expenses "
                        "WHERE clientid = %s AND type != 'income' AND statement_id = %s",
                        [clientid, max_stmt]
                    )
                else:
                    cursor.execute(
                        "SELECT field, value, frequency FROM client_expenses "
                        "WHERE clientid = %s AND type != 'income'",
                        [clientid]
                    )
                rows = cursor.fetchall()
                if rows:
                    for row in rows:
                        field, value, freq = row[0], self._pence(row[1]), row[2] or 'monthly'
                        monthly_val = self._normalise_to_monthly(value, freq)

                        # Convert pence to pounds for the breakdown
                        monthly_pounds = monthly_val / 100.0

                        if monthly_pounds > 0:
                            case.sfs_expenditure_breakdown.append({
                                "category": field.replace('_', ' ').title(),
                                "monthly_amount": monthly_pounds,
                                "bank_proven_amount": monthly_pounds,
                                "sfs_guideline_max": 0,
                            })
                            case.expenditure["total"] += monthly_val
                            if any(kw in field.lower() for kw in ("disability", "care", "medical")):
                                case.expenditure["disability_expenses"] += monthly_val
                    
                    logger.debug(f"Fetched {len(case.sfs_expenditure_breakdown)} expenditure items for {clientid}")
                    self._audit(case, "client_expenses (expenditure)", "FOUND", f"Fetched {len(rows)} items")
                else:
                    self._audit(case, "client_expenses (expenditure)", "EMPTY", "No expenditure entries found")
            except Exception as e:
                logger.debug(f"Failed to fetch expenditure data for clientid {clientid}: {e}")
                self._audit(case, "client_expenses (expenditure)", "ERROR", str(e))

    def _fetch_transaction_data(self, connection, case: CaseData, clientid: int) -> None:
        """Open Banking transaction data — table absent in this Aryza instance."""
        # schema-absent: client_open_banking_transactions not present
        case.gold_transactions = None
        self._audit(case, "client_open_banking_transactions", "SCHEMA-ABSENT",
                    "table absent from this Aryza instance")

    def _fetch_creditor_data(self, connection, case: CaseData, clientid: int) -> None:
        """Fetch creditor data from client_debt_new (primary) and iva_client_debt (secondary)."""
        case.total_unsecured_debt = 0  # Reset — will sum from actual creditor rows
        with connection.cursor() as cursor:
            # 1. PRIMARY: client_debt_new (the main live debt table)
            try:
                cursor.execute(
                    """SELECT cd.total, cd.monthly, cd.type, cd.ref, cd.from_credit_search,
                              COALESCE(c.name, 'Unknown Creditor') as creditor_name
                       FROM client_debt_new cd
                       LEFT JOIN creditor c ON c.id = cd.creditorid
                       WHERE cd.clientid = %s AND (cd.deleted IS NULL OR cd.deleted = 0)""",
                    [clientid]
                )
                rows = cursor.fetchall()
                if rows:
                    for row in rows:
                        balance = self._pence(row[0])
                        creditor_name = row[5]
                        creditor_ref = row[3] or f"debt_{row[2]}_{balance}"
                        is_hmrc = "hmrc" in creditor_name.lower() or "hm revenue" in creditor_name.lower()
                        raw_type = row[2] or "unsecured"
                        creditor = {
                            "name": creditor_name,
                            "balance": balance,
                            "account_reference": row[3] or "",
                            "linked_creditor": creditor_ref,
                            "account_open_date": None,
                            "last_transaction_date": None,
                            "creditor_type": self._normalise_hmrc_creditor_type(raw_type, creditor_name) if is_hmrc else raw_type,
                            "is_hmrc": is_hmrc,
                            "is_council": "council" in creditor_name.lower(),
                            "from_credit_report": bool(row[4]),
                        }
                        case.creditors.append(creditor)
                        case.total_unsecured_debt += balance
                    logger.debug(f"Fetched {len(rows)} debts from client_debt_new for clientid {clientid}")
                    self._audit(case, "client_debt_new", "FOUND", f"Fetched {len(rows)} debts")
                else:
                    self._audit(case, "client_debt_new", "EMPTY", "No debts found in client_debt_new")
            except Exception as e:
                logger.debug(f"Failed to fetch client_debt_new for clientid {clientid}: {e}")
                self._audit(case, "client_debt_new", "ERROR", str(e))

            # 2. SECONDARY: iva_client_debt (for IVA cases – only if no debts found yet)
            if not case.creditors:
                try:
                    cursor.execute(
                        """SELECT id.starting_balance, id.contractual_amount, id.type,
                                  id.account_ref,
                                  COALESCE(c.name, 'Unknown Creditor') as creditor_name
                           FROM iva_client_debt id
                           LEFT JOIN creditor c ON c.id = id.creditorid
                           WHERE id.clientid = %s AND (id.deleted IS NULL OR id.deleted = 0)""",
                        [clientid]
                    )
                    rows = cursor.fetchall()
                    if rows:
                        for row in rows:
                            balance = self._pence(row[0])
                            creditor_name = row[4]
                            creditor_ref = row[3] or f"iva_debt_{row[2]}_{balance}"
                            is_hmrc = "hmrc" in creditor_name.lower() or "hm revenue" in creditor_name.lower()
                            raw_type = row[2] or "unsecured"
                            creditor = {
                                "name": creditor_name,
                                "balance": balance,
                                "account_reference": row[3] or "",
                                "linked_creditor": creditor_ref,
                                "account_open_date": None,
                                "last_transaction_date": None,
                                "creditor_type": self._normalise_hmrc_creditor_type(raw_type, creditor_name) if is_hmrc else raw_type,
                                "is_hmrc": is_hmrc,
                                "is_council": "council" in creditor_name.lower(),
                                "from_credit_report": False,
                            }
                            case.creditors.append(creditor)
                            case.total_unsecured_debt += balance
                        logger.debug(f"Fetched {len(rows)} debts from iva_client_debt for clientid {clientid}")
                        self._audit(case, "iva_client_debt", "FOUND", f"Fetched {len(rows)} debts")
                    else:
                        self._audit(case, "iva_client_debt", "EMPTY", "No debts found in iva_client_debt")
                except Exception as e:
                    logger.debug(f"Failed to fetch iva_client_debt for clientid {clientid}: {e}")
                    self._audit(case, "iva_client_debt", "ERROR", str(e))
        
        logger.info(f"Creditors loaded for {clientid}: {[c['name'] for c in case.creditors]}")
    
    def _fetch_debt_arrangements(self, connection, case: CaseData, clientid: int) -> None:
        """Fetch existing debt arrangements and check for IVA."""
        with connection.cursor() as cursor:
            try:
                cursor.execute(
                    "SELECT arrangement_type FROM slam_debt_arrangments WHERE clientid = %s AND (deleted IS NULL OR deleted = 0)",
                    [clientid]
                )
                rows = cursor.fetchall()
                if rows:
                    for row in rows:
                        if row[0] and "iva" in row[0].lower():
                            case.flags["previous_iva"] = True
                            break
                    self._audit(case, "slam_debt_arrangments", "FOUND", f"Fetched {len(rows)} arrangements")
                else:
                    self._audit(case, "slam_debt_arrangments", "EMPTY", "No debt arrangements found")
            except Exception as e:
                logger.debug(f"Failed to fetch debt arrangements for clientid {clientid}: {e}")
                self._audit(case, "slam_debt_arrangments", "ERROR", str(e))
    
    def _fetch_property_data(self, connection, case: CaseData, clientid: int) -> None:
        """Fetch property details from slam_mortgage and slam_property_details."""
        with connection.cursor() as cursor:
            try:
                # Select mortgage balance from slam_mortgage and property value from slam_property_details
                # Sum both totals correctly even if multiple rows exist in either table
                cursor.execute(
                    """
                    SELECT 
                        (SELECT SUM(outstanding_total) FROM slam_mortgage WHERE clientid = %s) as mortgage_total,
                        (SELECT SUM(current_valuation) FROM slam_property_details WHERE clientid = %s) as property_total
                    """,
                    [clientid, clientid]
                )
                row = cursor.fetchone()
                if row and (row[0] is not None or row[1] is not None):
                    mortgage_total = row[0] or 0
                    property_value = row[1] or 0
                    
                    case.property["owns_property"] = True
                    case.property["mortgage_balance"] = self._pence(mortgage_total)
                    case.property["property_value"] = self._pence(property_value)
                    
                    # Calculate equity in pence
                    case.property["equity"] = case.property["property_value"] - case.property["mortgage_balance"]
                    
                    logger.debug(f"Property data fetched for {clientid}: value={case.property['property_value']}, mortgage={case.property['mortgage_balance']}")
                    self._audit(case, "slam_property/mortgage", "FOUND", f"Value: £{property_value}, Mortgage: £{mortgage_total}")
                else:
                    # No property data found in either table
                    case.property["owns_property"] = False
                    case.property["property_value"] = 0
                    case.property["mortgage_balance"] = 0
                    case.property["equity"] = 0
                    self._audit(case, "slam_property/mortgage", "EMPTY", "No property or mortgage data found")
            except Exception as e:
                logger.debug(f"Error fetching property data for clientid {clientid}: {e}")
                self._audit(case, "slam_property/mortgage", "ERROR", str(e))
    
    def _fetch_vehicle_data(self, connection, case: CaseData, clientid: int) -> None:
        """Fetch vehicle data including valuation and HP payments."""
        with connection.cursor() as cursor:
            try:
                # 1. Fetch from client_vehicle (slam_vehicle_details absent in this Aryza instance)
                cursor.execute(
                    """SELECT estimated_value, make, hp_monthly_amount, finance_start_date
                       FROM client_vehicle
                       WHERE clientid = %s AND deleted = 0 LIMIT 1""",
                    [clientid]
                )
                row = cursor.fetchone()
                if row:
                    case.vehicle["vehicle_value"] = self._pence(row[0])
                    case.vehicle["vehicle_make"] = row[1]
                    case.vehicle["hp_monthly_payment"] = self._pence(row[2])
                    case.vehicle["car_finance_start_date"] = self._format_date(row[3])
                    case.vehicle["has_vehicle"] = True
                    logger.debug(f"Vehicle data fetched for {clientid}: value={case.vehicle['vehicle_value']}")
                    self._audit(case, "client_vehicle", "FOUND", f"Value: £{row[0]}, Make: {row[1]}")
                else:
                    self._audit(case, "client_vehicle", "EMPTY", "No vehicles in client_vehicle")
            except Exception as e:
                logger.debug(f"Error fetching client_vehicle for {clientid}: {e}")
                self._audit(case, "client_vehicle", "ERROR", str(e))

            # 2. Fallback for HP payment from client_expenses
            if not case.vehicle.get("hp_monthly_payment"):
                try:
                    cursor.execute(
                        "SELECT value, frequency FROM client_expenses WHERE clientid = %s AND field LIKE '%%car_finance%%' LIMIT 1",
                        [clientid]
                    )
                    row = cursor.fetchone()
                    if row:
                        val = self._pence(row[0])
                        freq = row[1] or 'monthly'
                        case.vehicle["hp_monthly_payment"] = self._normalise_to_monthly(val, freq)
                        case.vehicle["has_vehicle"] = True
                        self._audit(case, "client_expenses (HP)", "FOUND", f"HP payment found: £{row[0]}")
                    else:
                        self._audit(case, "client_expenses (HP)", "EMPTY", "No HP payment found in expenses")
                except Exception as e:
                    logger.debug(f"Error fetching HP fallback for {clientid}: {e}")
                    self._audit(case, "client_expenses (HP)", "ERROR", str(e))
    
    def _fetch_flags_data(self, connection, case: CaseData, clientid: int) -> None:
        """Fetch flags: gambling, previous IVA, creditor questions."""
        with connection.cursor() as cursor:
            # Check for payday/gambling-type debts in client_debt_new
            try:
                cursor.execute(
                    "SELECT COUNT(*) FROM client_debt_new WHERE clientid = %s AND type = 'payday_loan' AND (deleted IS NULL OR deleted = 0)",
                    [clientid]
                )
                row = cursor.fetchone()
                if row and row[0] > 0:
                    case.flags["gambling_present"] = True
                    self._audit(case, "client_debt_new (payday)", "FOUND", f"{row[0]} payday loans found")
                else:
                    self._audit(case, "client_debt_new (payday)", "EMPTY", "No payday loans found")
            except Exception as e:
                logger.debug(f"No payday loan check for clientid {clientid}: {e}")
                self._audit(case, "client_debt_new (payday)", "ERROR", str(e))
            
            # Check for previous IVA in iva_client and factfind tables
            try:
                # 1. Check for a failed/terminated IVA recorded against this client's
                #    iva_client row. iva_client holds the client's own case (including
                #    the current one being assessed), so a row existing here is not
                #    itself evidence of a previous IVA — only a populated
                #    iva_failure_reason is.
                cursor.execute(
                    "SELECT iva_failure_reason FROM iva_client WHERE clientid = %s LIMIT 1",
                    [clientid]
                )
                row = cursor.fetchone()
                if row and row[0]:
                    case.flags["previous_iva"] = True
                    case.flags["previous_iva_failed_reason"] = row[0]
                    self._audit(case, "iva_client (IVA flag)", "FOUND", f"Reason: {row[0]}")
                else:
                    self._audit(case, "iva_client (IVA flag)", "EMPTY", "No previous IVA in iva_client")
                
                # 2. Check historical IVAs in factfind
                cursor.execute(
                    "SELECT reason_iva_failed FROM iva_factfind_have_you_ever_had_an_ivas WHERE clientid = %s LIMIT 1",
                    [clientid]
                )
                ff_row = cursor.fetchone()
                if ff_row:
                    case.flags["previous_iva"] = True
                    # Only overwrite reason if it's currently empty
                    if not case.flags.get("previous_iva_failed_reason"):
                        case.flags["previous_iva_failed_reason"] = ff_row[0]
                    self._audit(case, "iva_factfind_have_you_ever_had_an_ivas", "FOUND", f"Reason: {ff_row[0]}")
                else:
                    self._audit(case, "iva_factfind_have_you_ever_had_an_ivas", "EMPTY", "No previous IVA in factfind")
                
                # 3. factfind_vulnerability — schema-absent in this Aryza instance
                # vulnerability_flags defaults to {} / vulnerability_claimed defaults to False
                self._audit(case, "factfind_vulnerability", "SCHEMA-ABSENT",
                            "table absent from this Aryza instance")

                # 4. factfind_hmrc_details — schema-absent in this Aryza instance
                # hmrc_details defaults to None; seiss_debt_flag / trading flags remain unset
                self._audit(case, "factfind_hmrc_details", "SCHEMA-ABSENT",
                            "table absent from this Aryza instance")

                # client_flags — schema-absent in this Aryza instance (no SEISS fallback available)
                self._audit(case, "client_flags", "SCHEMA-ABSENT",
                            "table absent from this Aryza instance")

                # 5. factfind_transfers — schema-absent in this Aryza instance
                # antecedent_transactions defaults to False
                self._audit(case, "factfind_transfers", "SCHEMA-ABSENT",
                            "table absent from this Aryza instance")

                # 6. factfind_additional_flags — schema-absent in this Aryza instance
                # gamstop_registered / aoe_in_place remain unset
                self._audit(case, "factfind_additional_flags", "SCHEMA-ABSENT",
                            "table absent from this Aryza instance")
            except Exception as e:
                logger.debug(f"Error checking flags tables for clientid {clientid}: {e}")
                self._audit(case, "flags_check", "ERROR", str(e))
    
    # ========================================================================
    # HELPER METHODS - DATA TRANSFORMATION
    # ========================================================================
    
    @staticmethod
    def _normalise_hmrc_creditor_type(raw_type: str, creditor_name: str) -> str:
        """For HMRC creditors, infer sub-type from the creditor name when Aryza stores
        a generic type (e.g. 'unsecured').  Returns the raw_type unchanged for non-HMRC
        creditors or when the raw_type already identifies the sub-type."""
        _GENERIC = {"unsecured", "other", "", None}
        if raw_type not in _GENERIC:
            return raw_type
        name = creditor_name.lower()
        if "vat" in name:
            return "vat"
        if "paye" in name:
            return "paye"
        if "self assessment" in name or "self-assessment" in name:
            return "self_assessment"
        if "tax credit" in name:
            return "tax_credit"
        if "national insurance" in name or " ni " in name:
            return "national_insurance"
        return raw_type

    def _pence(self, pounds: Any) -> int:
        """Convert pounds (Decimal) to pence (int)."""
        if pounds is None:
            return 0
        try:
            if isinstance(pounds, Decimal):
                return int(pounds * 100)
            else:
                return int(float(pounds) * 100)
        except (ValueError, TypeError):
            logger.warning(f"Unable to convert {pounds} to pence")
            return 0
    
    def _normalise_to_monthly(self, pence_amount: int, frequency: str) -> int:
        """Convert a pence amount from its given frequency to a monthly equivalent."""
        freq = (frequency or 'monthly').lower()
        if freq == 'weekly':
            return int(pence_amount * 52 / 12)
        elif freq in ('fortnightly', '2_weekly'):
            return int(pence_amount * 26 / 12)
        elif freq in ('4_weekly', 'four_weekly', 'lunar_monthly'):
            return int(pence_amount * 13 / 12)
        elif freq in ('annually', 'annual', 'yearly'):
            return int(pence_amount / 12)
        # default: monthly
        return pence_amount
    
    def _build_creditor_dict(self, name: str, balance: Any, start_date: Any,
                            monthly_payment: Any, account_number: str,
                            creditor_type: str, from_equifax: Any) -> Dict[str, Any]:
        """Build creditor dictionary with all fields."""
        creditor_name = name or "Unknown"
        return {
            "name": creditor_name,
            "balance": self._pence(balance),
            "account_reference": account_number or "",
            "account_open_date": self._format_date(start_date),
            "last_transaction_date": None,
            "creditor_type": creditor_type or "other",
            "is_hmrc": "hmrc" in creditor_name.lower() or "hm revenue" in creditor_name.lower(),
            "is_council": "council" in creditor_name.lower(),
            "from_credit_report": bool(from_equifax),
        }
    
    def _format_date(self, date_value: Any) -> Optional[str]:
        """Convert database date to ISO format string."""
        if date_value is None:
            return None
        
        if isinstance(date_value, str):
            # Already a string, try to parse and reformat
            try:
                if date_value.isdigit() and len(date_value) == 10:
                    # Unix timestamp
                    dt = datetime.fromtimestamp(int(date_value))
                    return dt.isoformat()
                else:
                    return date_value
            except Exception:
                return date_value
        
        if isinstance(date_value, (int, float)):
            # Unix timestamp
            try:
                dt = datetime.fromtimestamp(date_value)
                return dt.isoformat()
            except Exception:
                return None
        
        if isinstance(date_value, datetime):
            return date_value.isoformat()
        
        return None
    
    def _parse_children_ages(self, case: CaseData, ages_str: str) -> None:
        """Parse children ages from comma-separated string."""
        if not ages_str:
            return
        
        try:
            # Split by comma and strip whitespace
            age_list = [s.strip() for s in ages_str.split(",")]
            for age_str in age_list:
                if age_str.isdigit():
                    age = int(age_str)
                    if 0 <= age <= 120:  # Sanity check
                        case.dependants.append({"age": age})
        except Exception as e:
            logger.warning(f"Failed to parse children ages '{ages_str}': {e}")
    
    def _calculate_totals(self, case: CaseData) -> None:
        """Calculate total income, expenditure and disposable income."""
        case.income["total"] = (
            case.income["employment"] +
            case.income["universal_credit"] +
            case.income["dla"] +
            case.income["pip"] +
            case.income["other_benefits"] +
            case.income["third_party_contribution"]
        )
        
        # disability_expenses is added on top of expenses already accumulated
        # by the loop at line 590 — do NOT overwrite the accumulated total.
        case.expenditure["total"] += case.expenditure["disability_expenses"]

        # Always recalculate — td_client contribution may be stale or zero
        if case.income["total"] > 0:
            case.disposable_income = max(0, case.income["total"] - case.expenditure["total"])
            logger.debug(f"Calculated disposable_income={case.disposable_income}")
        else:
            # Income not found — td_client may hold a negative contribution figure.
            # Clamp to 0 so the engine receives "unknown" (0) rather than a nonsense
            # negative value that would produce a misleading displayed DI.
            if case.disposable_income < 0:
                case.disposable_income = 0


# ============================================================================
# PUBLIC API
# ============================================================================

def fetch_case_by_reference(reference: str) -> CaseData:
    """
    Public API to fetch case data by reference.
    
    Args:
        reference: Client reference number
    
    Returns:
        CaseData object
    
    Raises:
        AryzaCaseNotFoundError: If client not found
        AryzaConnectionError: If database connection fails
        AryzaDataError: If data retrieval fails
    """
    client = AryzaClient()
    return client.fetch_case_by_reference(reference)
