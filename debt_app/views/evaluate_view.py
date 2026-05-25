import logging
import dataclasses
from datetime import datetime
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from debt_app.aryza_client import (
    fetch_case_by_reference,
    AryzaCaseNotFoundError,
    AryzaConnectionError,
    AryaTimeoutError,
    AryzaDataError,
)
from debt_app.criteria_engine import assess_case
from debt_app.helpers import CREDITOR_ALIAS_MAP
from debt_app.recommendation_engine import get_recommendation
from debt_app.models import CriteriaDecision, GlobalCriteria, Application

logger = logging.getLogger(__name__)


class EvaluateCaseView(APIView):
    """
    POST /api/v1/cases/<case_id>/evaluate
    Triggers the criteria engine for a specific case and returns a structured evaluation.
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, case_id):
        # 1. Lookup Application to get Aryza reference
        try:
            application = Application.objects.get(id=case_id)
        except Application.DoesNotExist:
            return self._error_response("Application not found", "CASE_NOT_FOUND", status.HTTP_404_NOT_FOUND)
        aryza_ref = application.aryza_reference

        # 2. Fetch case data from Aryza
        try:
            case_data_obj = fetch_case_by_reference(aryza_ref)
            
            # Transform CaseData object into the payload format expected by the criteria engine
            case_data = self._prepare_engine_payload(case_data_obj)
            
        except AryzaCaseNotFoundError:
            return self._error_response("Case not found in Aryza", "CASE_NOT_FOUND", status.HTTP_404_NOT_FOUND)
        except (AryaTimeoutError, AryzaConnectionError, AryzaDataError) as e:
            logger.error(f"Aryza error for {aryza_ref} (app {case_id}): {str(e)}")
            return self._error_response(f"Aryza error: {str(e)}", "ARYZA_ERROR", status.HTTP_500_INTERNAL_SERVER_ERROR)
        except Exception as e:
            logger.exception(f"Unexpected error fetching case {aryza_ref} (app {case_id})")
            return self._error_response("Internal server error", "INTERNAL_ERROR", status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 2. Check for fundamentally missing data (422)
        # If total_unsecured_debt is missing or None, we can't really evaluate.
        if case_data.get("total_unsecured_debt") is None:
            return self._error_response("Required case fields missing from Aryza", "INCOMPLETE_DATA", status.HTTP_422_UNPROCESSABLE_ENTITY)

        # 3. Pass case data into the existing criteria engine
        try:
            # assess_case expects the payload format constructed by _prepare_engine_payload
            engine_output = assess_case(case_data)
        except Exception as e:
            logger.exception(f"Criteria engine error for case {case_id}")
            return self._error_response("Criteria engine failure", "ENGINE_ERROR", status.HTTP_500_INTERNAL_SERVER_ERROR)

        # 4. Map engine output to the new decision field
        decision = self._determine_decision(engine_output, case_data)

        # 5. Get recommendations
        recommendations = get_recommendation(decision, engine_output, case_data)

        # 6. Map engine output to criteria_results[]
        # Fetch rule names for mapping
        rule_names = {r.rule_key: r.rule_name for r in GlobalCriteria.objects.all()}
        criteria_results = self._map_criteria_results(engine_output, rule_names)

        # 7. Construct final response
        response_data = {
            "case_id": case_id,
            "application_id": aryza_ref,
            "evaluation_id": None,  # Will be set after persistence
            "decision": decision,
            "criteria_results": criteria_results,
            "recommended_solution": recommendations.get("recommended_solution"),
            "alternative_solutions": recommendations.get("alternative_solutions", []),
            "requires_review": decision == "REFERRED",
            "flagged_criteria": [r["criterion_id"] for r in criteria_results if r["result"] == "FLAG"],
            "evaluated_at": timezone.now().isoformat(),
            "creditors": [
                {
                    "name": c.get("name", "Unknown Creditor"),
                    "balance": float(c.get("balance", 0))
                } for c in case_data.get("creditors", [])
            ],
            "total_unsecured_debt": float(case_data.get("total_unsecured_debt", 0)),
            "disposable_income": float(case_data.get("disposable_income", 0))
        }

        # 8. Persist the result to CriteriaDecision model
        try:
            # engine_output contains dataclass objects that are not JSON serializable
            serialized_output = self._serialize_engine_output(engine_output)
            
            # Clear previous history for this reference to satisfy "no history" requirement
            CriteriaDecision.objects.filter(application_id=case_id).delete()
            
            decision_record = CriteriaDecision.objects.create(
                application_id=case_id,
                client_name=case_data.get("client_name", "Unknown"),
                input_snapshot=case_data,
                decision_output=serialized_output, # Serialized engine output
                result_json=response_data,         # The new standardized format
                recommended_solution=recommendations.get("recommended_solution", {}).get("code", "UNCLEAR") if recommendations.get("recommended_solution") else "UNCLEAR",
                passes_all_hard_blocks=len(engine_output.get("hard_blocks", [])) == 0,
                triggered_by=request.user,
                source="CASE_ASSESSMENT"
            )
            response_data["evaluation_id"] = str(decision_record.id)
            # Update result_json with the ID
            decision_record.result_json = response_data
            decision_record.save(update_fields=["result_json"])
        except Exception as e:
            logger.error(f"Failed to persist CriteriaDecision for {case_id}: {e}")
            # We still return the response even if persistence fails, but we log it

        return Response(response_data, status=status.HTTP_200_OK)

    LINK_FINANCIAL_VARIANTS = { 
        "link financial outsourcing limited", 
        "link financial ltd", 
        "link financial", 
        "link financial outsourcing", 
    }

    def _prepare_engine_payload(self, case_data_obj):
        """
        Transforms Aryza CaseData object into the payload format expected by the criteria engine.
        Converts pence (int) to pounds (float).
        """
        # Convert pence to pounds for all financial fields
        di_pounds = case_data_obj.disposable_income / 100.0
        
        # Calculate unsecured debt excluding HP/secured debts
        unsecured_debt_pounds = sum( 
            c["balance"] / 100.0 
            for c in case_data_obj.creditors 
            if "hp" not in c["name"].lower() 
            and c.get("creditor_type", "unsecured").lower() not in ("hp", "hire_purchase", "secured") 
        )
        
        # Build the engine payload matching CASE_ASSESSMENT_PAYLOAD.md
        payload = {
            "application_id": case_data_obj.aryza_reference,
            "aryza_reference": case_data_obj.aryza_reference,
            "client_name": case_data_obj.client_name,
            "employment_status": case_data_obj.employment_status,
            "disposable_income": di_pounds,
            "total_unsecured_debt": unsecured_debt_pounds,
            "financial_summary": {
                "net_balance": di_pounds,
                "total_income": case_data_obj.income["total"] / 100.0,
                "income_source": case_data_obj.employment_status,
            },
            "crm_data": {
                "total_unsecured_debt": unsecured_debt_pounds,
            },
            "clientInfo": {
                "client_name": case_data_obj.client_name,
                "dateOfBirth": case_data_obj.dob,
                "is_employed": case_data_obj.employment_status == "employed",
            },
            "creditors": [
                {
                    "name": ( 
                        "link financial outsourcing" 
                        if c["name"].lower().strip() in self.LINK_FINANCIAL_VARIANTS 
                        else c["name"].lower().strip() 
                    ), 
                    "creditor_name": ( 
                        "link financial outsourcing" 
                        if c["name"].lower().strip() in self.LINK_FINANCIAL_VARIANTS 
                        else c["name"].lower().strip() 
                    ), 
                    "balance": c["balance"] / 100.0,
                    "creditor_type": c.get("creditor_type", "unsecured"),
                    "last_payment_date": c.get("last_payment_date"),
                    "first_payment_made": c.get("first_payment_made", False),
                    "account_age_months": c.get("account_age_months"),
                    "linked_creditor": c.get("linked_creditor"),
                    "is_hire_purchase": "hp" in c["name"].lower() or c.get("creditor_type", "").lower() in ("hp", "hire_purchase", "secured"),
                } for c in case_data_obj.creditors
                if "hp" not in c["name"].lower() 
                and c.get("creditor_type", "unsecured").lower() not in ("hp", "hire_purchase", "secured")
            ],
            "income": {k: v/100.0 for k, v in case_data_obj.income.items()},
            "expenditure": {k: v/100.0 for k, v in case_data_obj.expenditure.items()},
            "property": {
                "owns_property": case_data_obj.property.get("owns_property", False),
                "property_value": (case_data_obj.property.get("property_value") or 0) / 100.0 if case_data_obj.property.get("property_value") else None,
                "mortgage_balance": (case_data_obj.property.get("mortgage_balance") or 0) / 100.0 if case_data_obj.property.get("mortgage_balance") else None,
                "equity": (case_data_obj.property.get("equity") or 0) / 100.0 if case_data_obj.property.get("equity") else None,
            },
            "vehicle": {
                "has_vehicle": case_data_obj.vehicle.get("has_vehicle", False),
                "vehicle_value": (case_data_obj.vehicle.get("vehicle_value") or 0) / 100.0 if case_data_obj.vehicle.get("vehicle_value") else None,
                "hp_monthly_payment": (case_data_obj.vehicle.get("hp_monthly_payment") or 0) / 100.0 if case_data_obj.vehicle.get("hp_monthly_payment") else None,
            },
            # Top-level fields expected by criteria_engine.py
            "vehicle_value": (case_data_obj.vehicle.get("vehicle_value") or 0) / 100.0 if case_data_obj.vehicle.get("vehicle_value") else None,
            "has_vehicle": case_data_obj.vehicle.get("has_vehicle", False),
            "children": case_data_obj.dependants,
            "antecedent_transactions": case_data_obj.flags.get("antecedent_transactions", False),
            "seiss_debt_flag": case_data_obj.flags.get("seiss_debt_flag"),
            "vulnerability_claimed": case_data_obj.flags.get("vulnerability_claimed", False),
            "previous_iva": case_data_obj.flags.get("previous_iva", False),
            "previous_iva_failed_reason": case_data_obj.flags.get("previous_iva_failed_reason"),
            "disability_income": (case_data_obj.income.get("dla", 0) + case_data_obj.income.get("pip", 0)) / 100.0,
            "disability_expenses": case_data_obj.expenditure.get("disability_expenses", 0) / 100.0,
            "third_party_contribution": case_data_obj.income.get("third_party_contribution", 0) / 100.0,
            "bankruptcy_return": None,  # Not currently fetched from Aryza
            "is_currently_trading": case_data_obj.flags.get("is_currently_trading"),
            "has_vat_arrangement": case_data_obj.flags.get("has_vat_arrangement"),
            "employer_paye_obligations_current": case_data_obj.flags.get("employer_paye_obligations_current"),
            "income_is_benefits_only": case_data_obj.employment_status == "benefits_only",
            "receives_any_benefits": (
                case_data_obj.income.get("universal_credit", 0) > 0 or 
                case_data_obj.income.get("dla", 0) > 0 or 
                case_data_obj.income.get("pip", 0) > 0 or 
                case_data_obj.income.get("other_benefits", 0) > 0
            ),
            "gamstop_registered": case_data_obj.flags.get("gamstop_registered", False),
            "aoe_in_place": case_data_obj.flags.get("aoe_in_place", False),
            "gold_transactions": case_data_obj.gold_transactions,
            "sfs_expenditure_breakdown": case_data_obj.sfs_expenditure_breakdown,
            "flags": case_data_obj.flags,
            "dependants": case_data_obj.dependants,
        }
             
        return payload

    def _serialize_engine_output(self, obj):
        """
        Recursively converts RuleResult (dataclass), Decimal, set, etc. 
        into JSON-serializable formats.
        """
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, (set, tuple)):
            return list(obj)
        if isinstance(obj, dict):
            return {str(k): self._serialize_engine_output(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._serialize_engine_output(i) for i in obj]
        return obj

    def _determine_decision(self, engine_output, case_data):
        """
        Applies the decision logic mapping.
        """
        hard_blocks = engine_output.get("hard_blocks", [])
        flags = engine_output.get("flags", [])

        # Check for incomplete data first
        # Baseline required fields for Phase 1
        required_fields = ["total_unsecured_debt", "disposable_income"]
        for field in required_fields:
            val = case_data.get(field)
            if val is None:
                return "INCOMPLETE"

        if hard_blocks:
            return "INELIGIBLE"
        
        if flags:
            return "REFERRED"
        
        return "ELIGIBLE"

    def _map_criteria_results(self, engine_output, rule_names):
        """
        Maps engine output to criteria_results list.
        """
        results = []

        # Map hard_blocks -> FAIL
        for hb in engine_output.get("hard_blocks", []):
            results.append({
                "criterion_id": hb.rule_id,
                "name": rule_names.get(hb.rule_id, hb.rule_id),
                "result": "FAIL",
                "message": hb.message,
                "value_checked": hb.actual_value
            })

        # Map flags -> FLAG
        for fl in engine_output.get("flags", []):
            results.append({
                "criterion_id": fl.rule_id,
                "name": rule_names.get(fl.rule_id, fl.rule_id),
                "result": "FLAG",
                "message": fl.message,
                "value_checked": fl.actual_value
            })

        # Map passed -> PASS
        for ps in engine_output.get("passed", []):
            results.append({
                "criterion_id": ps.rule_id,
                "name": rule_names.get(ps.rule_id, ps.rule_id),
                "result": "PASS",
                "message": ps.message,
                "value_checked": ps.actual_value
            })

        return results

    def _error_response(self, message, code, status_code, field=None):
        error_data = {
            "error": {
                "code": code,
                "message": message
            }
        }
        if field:
            error_data["error"]["field"] = field
        return Response(error_data, status=status_code)
