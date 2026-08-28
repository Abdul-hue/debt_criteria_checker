"""Voter (creditor representative) records."""

from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from debt_app.models import Voter

def _voter_to_dict(v):
    return {
        "id": v.id,
        "name": v.name,
        "is_joint": v.is_joint,
        "last_payment_date": v.last_payment_date.isoformat() if v.last_payment_date else None,
        "first_payment_made": v.first_payment_made,
        "vehicle_arrears_months": v.vehicle_arrears_months,
        "ie_matches_loan_application": v.ie_matches_loan_application,
        "arrangement_confirmed_before_proposing": v.arrangement_confirmed_before_proposing,
        "client_still_has_asset_in_possession": v.client_still_has_asset_in_possession,
        "is_grant_overpayment": v.is_grant_overpayment,
        "guarantee_called_up": v.guarantee_called_up,
    }


_VOTER_WRITABLE_FIELDS = [
    'name', 'is_joint', 'last_payment_date', 'first_payment_made',
    'vehicle_arrears_months', 'ie_matches_loan_application',
    'arrangement_confirmed_before_proposing', 'client_still_has_asset_in_possession',
    'is_grant_overpayment', 'guarantee_called_up',
]


class VoterListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 100)), 500)
        search = request.query_params.get('search', '')

        queryset = Voter.objects.all().order_by('name')
        if search:
            queryset = queryset.filter(name__icontains=search)

        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": [_voter_to_dict(v) for v in page_obj],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        if not data.get('name'):
            return Response({"detail": "name is required."}, status=status.HTTP_400_BAD_REQUEST)

        voter = Voter()
        for field in _VOTER_WRITABLE_FIELDS:
            if field in data:
                setattr(voter, field, data[field])

        try:
            voter.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        voter.save()
        return Response(_voter_to_dict(voter), status=status.HTTP_201_CREATED)


class VoterDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def _get_object(self, pk):
        try:
            return Voter.objects.get(id=pk)
        except Voter.DoesNotExist:
            return None

    def get(self, request, pk):
        voter = self._get_object(pk)
        if voter is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_voter_to_dict(voter), status=status.HTTP_200_OK)

    def put(self, request, pk):
        voter = self._get_object(pk)
        if voter is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        for field in _VOTER_WRITABLE_FIELDS:
            if field in request.data:
                setattr(voter, field, request.data[field])

        try:
            voter.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        voter.save()
        return Response(_voter_to_dict(voter), status=status.HTTP_200_OK)

    def delete(self, request, pk):
        voter = self._get_object(pk)
        if voter is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        voter.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
