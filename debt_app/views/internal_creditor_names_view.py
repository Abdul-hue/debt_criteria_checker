"""
Token-free creditor NAME directory for the case-assessment (CA) backend.

GET /api/v1/criteria/internal/creditor-names/

Every ACTIVE creditor that has trading names, as
`{"count": n, "results": [{"name": creditor_name, "trading_names": [...]}]}`.

Why (2026-11-25): CA joins an Aryza debt to the credit report's account by
name. A brand no spelling links to its lender ("RBS" / "Royal Bank of
Scotland") is already recorded here, in each row's `trading_names`, for the
criteria lookup. CA reads this to learn the same names -- as a name clue only,
never a criteria decision (`helpers._get_creditor_by_trading_name_uncached`
stays the only resolver of which criteria apply).

Same posture as the internal SFS routes (`internal_sfs_views.py`): open to
callers on the server, READ ONLY -- names only, no criteria, no case data. A
row with no trading names teaches nothing and is left out.
"""
from rest_framework import status
from rest_framework.response import Response

from debt_app.models import CreditorCriteria
from debt_app.views.internal_sfs_views import _OpenAPIView


class InternalCreditorNamesView(_OpenAPIView):
    http_method_names = ["get", "head", "options"]

    def get(self, request):
        rows = (CreditorCriteria.objects.filter(is_active=True)
                .order_by("id").values_list("creditor_name", "trading_names"))
        results = []
        for name, trading in rows:
            names = [str(t).strip() for t in (trading or []) if str(t or "").strip()]
            if name and names:
                results.append({"name": name, "trading_names": names})
        return Response({"count": len(results), "results": results}, status=status.HTTP_200_OK)
