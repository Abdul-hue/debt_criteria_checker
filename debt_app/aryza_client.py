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


# ============================================================================
# TYPE DEFINITIONS
# ============================================================================

class CaseData:
    """Data transfer object for case information from Aryza."""
    
    def __init__(self):
        self.aryza_reference: str = ""
        self.clientid: int = 0
        self.client_name: str = ""
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
        self.property: Dict[str, Any] = {
            "owns_property": False,
            "property_value": None,
            "mortgage_balance": None,
            "equity": None,
        }
        self.vehicle: Dict[str, Any] = {
            "has_vehicle": False,
            "vehicle_value": None,
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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "aryza_reference": self.aryza_reference,
            "clientid": self.clientid,
            "client_name": self.client_name,
            "employment_status": self.employment_status,
            "total_unsecured_debt": self.total_unsecured_debt,
            "disposable_income": self.disposable_income,
            "creditors": self.creditors,
            "income": self.income,
            "expenditure": self.expenditure,
            "property": self.property,
            "vehicle": self.vehicle,
            "flags": self.flags,
            "dependants": self.dependants,
        }


# ============================================================================
# ARYZA CLIENT
# ============================================================================

class AryzaClient:
    """Client for querying read-only Aryza database."""
    
    def __init__(self):
        self.db_alias = "aryza"
    
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
                    "SELECT id, firstname, lastname FROM client WHERE id = %s LIMIT 1",
                    [clientid]
                )
                client_row = cursor.fetchone()
                if client_row:
                    fname = client_row[1] or ""
                    lname = client_row[2] or ""
                    case.client_name = f"{fname} {lname}".strip() or f"Client {clientid}"
                else:
                    case.client_name = f"Client {clientid}"
            except Exception as e:
                logger.warning(f"Failed to fetch client name for clientid {clientid}: {e}")
                case.client_name = f"Client {clientid}"
            
            # Try td_client for summary totals (may be empty in TIG)
            try:
                cursor.execute(
                    "SELECT td_total_debt, td_contribution, td_third_party_contribution, "
                    "       td_no_cars, td_previous_bankruptcy, td_third_party_contributor "
                    "FROM td_client WHERE clientid = %s",
                    [clientid]
                )
                td_row = cursor.fetchone()
                if td_row:
                    if td_row[0] is not None:
                        case.total_unsecured_debt = self._pence(td_row[0])
                    if td_row[1] is not None:
                        case.disposable_income = self._pence(td_row[1])
                    case.income["third_party_contribution"] = self._pence(td_row[2])
                    case.vehicle["has_vehicle"] = bool(td_row[3] and td_row[3] > 0)
                    case.flags["previous_iva"] = bool(td_row[4])
                    case.flags["has_third_party"] = bool(td_row[5])
            except Exception as e:
                logger.debug(f"td_client not available for clientid {clientid}: {e}")
    
    def _fetch_income_data(self, connection, case: CaseData, clientid: int) -> None:
        """Fetch income data from client_income table (wide-column format)."""
        with connection.cursor() as cursor:
            try:
                cursor.execute(
                    """SELECT 
                        earnings_net, earnings_net_frequency,
                        earnings_partner_net,
                        benefit_universal_credit, benefit_universal_credit_frequency,
                        benefit_dla, benefit_dla_frequency,
                        benefit_pip, benefit_pip_frequency,
                        benefit_child, benefit_housing, benefit_income_support,
                        benefit_working_tax_credit, benefit_child_tax_credit,
                        benefit_esa, benefit_carers_allowance,
                        pension_state, pension_client, pension_private, pension_credit,
                        non_dependant_contributions, lodger_income
                    FROM client_income WHERE clientid = %s LIMIT 1""",
                    [clientid]
                )
                row = cursor.fetchone()
                if row:
                    # Employment income (normalise to monthly)
                    emp_net = self._pence(row[0])
                    emp_freq = row[1] or 'monthly'
                    emp_partner = self._pence(row[2])
                    case.income["employment"] = (
                        self._normalise_to_monthly(emp_net, emp_freq) +
                        self._normalise_to_monthly(emp_partner, 'monthly')
                    )
                    
                    # Universal Credit
                    uc_amt = self._pence(row[3])
                    uc_freq = row[4] or 'monthly'
                    case.income["universal_credit"] = self._normalise_to_monthly(uc_amt, uc_freq)
                    
                    # DLA
                    dla_amt = self._pence(row[5])
                    dla_freq = row[6] or 'monthly'
                    case.income["dla"] = self._normalise_to_monthly(dla_amt, dla_freq)
                    
                    # PIP
                    pip_amt = self._pence(row[7])
                    pip_freq = row[8] or 'monthly'
                    case.income["pip"] = self._normalise_to_monthly(pip_amt, pip_freq)
                    
                    # Other benefits (child, housing, income support, tax credits, ESA, carer)
                    other = sum(self._pence(v) for v in row[9:16] if v is not None)
                    case.income["other_benefits"] = other
                    
                    # Third-party contributions (lodger, non-dependant)
                    tp = sum(self._pence(v) for v in [row[20], row[21]] if v is not None)
                    if tp > 0 and case.income["third_party_contribution"] == 0:
                        case.income["third_party_contribution"] = tp
                    
                    # Determine employment status
                    if case.income["employment"] > 0:
                        case.employment_status = "employed"
                    elif case.income["universal_credit"] + case.income["dla"] + case.income["pip"] + case.income["other_benefits"] > 0:
                        case.employment_status = "benefits_only"
                    
                    logger.debug(f"Income fetched for {clientid}: emp={case.income['employment']}, uc={case.income['universal_credit']}")
            except Exception as e:
                logger.debug(f"Failed to fetch client_income for clientid {clientid}: {e}")
            
            # Fallback: try client_expenses for income type entries
            try:
                cursor.execute(
                    "SELECT field, value, frequency FROM client_expenses WHERE clientid = %s AND type = 'income'",
                    [clientid]
                )
                for row in cursor.fetchall():
                    field, value, freq = row[0], self._pence(row[1]), row[2] or 'monthly'
                    monthly_val = self._normalise_to_monthly(value, freq)
                    if 'earnings' in field or 'employment' in field:
                        case.income["employment"] += monthly_val
                    elif 'universal_credit' in field:
                        case.income["universal_credit"] += monthly_val
                    elif 'dla' in field:
                        case.income["dla"] += monthly_val
                    elif 'pip' in field:
                        case.income["pip"] += monthly_val
                    else:
                        case.income["other_benefits"] += monthly_val
            except Exception as e:
                logger.debug(f"Failed to fetch client_expenses income fallback for clientid {clientid}: {e}")
    
    def _fetch_creditor_data(self, connection, case: CaseData, clientid: int) -> None:
        """Fetch creditor data from client_debt_new (primary) and iva_client_debt (secondary)."""
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
                for row in rows:
                    balance = self._pence(row[0])
                    creditor_name = row[5]
                    creditor = {
                        "name": creditor_name,
                        "balance": balance,
                        "account_reference": "",
                        "account_open_date": None,
                        "last_transaction_date": None,
                        "creditor_type": row[2] or "unsecured",
                        "is_hmrc": "hmrc" in creditor_name.lower() or "hm revenue" in creditor_name.lower(),
                        "is_council": "council" in creditor_name.lower(),
                        "from_credit_report": bool(row[4]),
                    }
                    case.creditors.append(creditor)
                    case.total_unsecured_debt += balance
                logger.debug(f"Fetched {len(rows)} debts from client_debt_new for clientid {clientid}")
            except Exception as e:
                logger.debug(f"Failed to fetch client_debt_new for clientid {clientid}: {e}")

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
                    for row in rows:
                        balance = self._pence(row[0])
                        creditor_name = row[4]
                        creditor = {
                            "name": creditor_name,
                            "balance": balance,
                            "account_reference": row[3] or "",
                            "account_open_date": None,
                            "last_transaction_date": None,
                            "creditor_type": row[2] or "unsecured",
                            "is_hmrc": "hmrc" in creditor_name.lower() or "hm revenue" in creditor_name.lower(),
                            "is_council": "council" in creditor_name.lower(),
                            "from_credit_report": False,
                        }
                        case.creditors.append(creditor)
                        case.total_unsecured_debt += balance
                    logger.debug(f"Fetched {len(rows)} debts from iva_client_debt for clientid {clientid}")
                except Exception as e:
                    logger.debug(f"Failed to fetch iva_client_debt for clientid {clientid}: {e}")
    
    def _fetch_debt_arrangements(self, connection, case: CaseData, clientid: int) -> None:
        """Fetch existing debt arrangements and check for IVA."""
        with connection.cursor() as cursor:
            try:
                cursor.execute(
                    "SELECT arrangement_type FROM slam_debt_arrangments WHERE clientid = %s AND (deleted IS NULL OR deleted = 0)",
                    [clientid]
                )
                rows = cursor.fetchall()
                for row in rows:
                    if row[0] and "iva" in row[0].lower():
                        case.flags["previous_iva"] = True
                        break
            except Exception as e:
                logger.debug(f"Failed to fetch debt arrangements for clientid {clientid}: {e}")
    
    def _fetch_property_data(self, connection, case: CaseData, clientid: int) -> None:
        """Fetch property details from slam_mortgage (live table)."""
        with connection.cursor() as cursor:
            # Check slam_mortgage first (main property table)
            try:
                cursor.execute(
                    "SELECT COUNT(*) FROM slam_mortgage WHERE clientid = %s",
                    [clientid]
                )
                row = cursor.fetchone()
                if row and row[0] > 0:
                    case.property["owns_property"] = True
                    logger.debug(f"Mortgage/property found for clientid {clientid}")
            except Exception as e:
                logger.debug(f"No mortgage data for clientid {clientid}: {e}")
    
    def _fetch_vehicle_data(self, connection, case: CaseData, clientid: int) -> None:
        """Fetch vehicle data - already partially set from td_client."""
        # Vehicle data mainly comes from td_client (td_no_cars)
        pass
    
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
            except Exception as e:
                logger.debug(f"No payday loan check for clientid {clientid}: {e}")
            
            # Check for previous IVA in iva_client table
            try:
                cursor.execute(
                    "SELECT COUNT(*) FROM iva_client WHERE clientid = %s",
                    [clientid]
                )
                row = cursor.fetchone()
                if row and row[0] > 0:
                    case.flags["previous_iva"] = True
            except Exception as e:
                logger.debug(f"No iva_client check for clientid {clientid}: {e}")
    
    # ========================================================================
    # HELPER METHODS - DATA TRANSFORMATION
    # ========================================================================
    
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
        
        case.expenditure["total"] = case.expenditure["disability_expenses"]
        
        # If disposable_income was not set by td_client, calculate it
        if case.disposable_income == 0 and case.income["total"] > 0:
            case.disposable_income = max(0, case.income["total"] - case.expenditure["total"])
            logger.debug(f"Calculated disposable_income={case.disposable_income} from income-expenditure")


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
