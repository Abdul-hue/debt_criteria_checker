"""Evidence ledger entries."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from debt_app.models import Application
from debt_app.models import EvidenceLedger
from debt_app.permissions import HasFeatureAccess

def _evidence_to_dict(e):
    return {
        "id": e.id,
        "application": e.application_id,
        "entry_type": e.entry_type,
        "created_at": e.created_at.isoformat(),
    }


class EvidenceLedgerListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, HasFeatureAccess]
    required_feature = 'evidence'

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 100)), 500)
        application_id = request.query_params.get('application_id')

        queryset = EvidenceLedger.objects.all().order_by('-created_at')
        if application_id:
            queryset = queryset.filter(application_id=application_id)

        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": [_evidence_to_dict(e) for e in page_obj],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        required = ['application', 'entry_type']
        for field in required:
            if not data.get(field):
                return Response({"detail": f"{field} is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            app = Application.objects.get(id=data['application'])
        except Application.DoesNotExist:
            return Response({"detail": "Application not found."}, status=status.HTTP_400_BAD_REQUEST)

        evidence = EvidenceLedger(
            application=app,
            entry_type=data['entry_type'],
        )

        try:
            evidence.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        evidence.save()
        return Response(_evidence_to_dict(evidence), status=status.HTTP_201_CREATED)


class EvidenceLedgerDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def _get_object(self, pk):
        try:
            return EvidenceLedger.objects.get(id=pk)
        except EvidenceLedger.DoesNotExist:
            return None

    def get(self, request, pk):
        evidence = self._get_object(pk)
        if evidence is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_evidence_to_dict(evidence), status=status.HTTP_200_OK)

    def put(self, request, pk):
        evidence = self._get_object(pk)
        if evidence is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if 'entry_type' in request.data:
            evidence.entry_type = request.data['entry_type']

        if 'application' in request.data:
            try:
                evidence.application = Application.objects.get(id=request.data['application'])
            except Application.DoesNotExist:
                return Response({"detail": "Application not found."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            evidence.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        evidence.save()
        return Response(_evidence_to_dict(evidence), status=status.HTTP_200_OK)

    def delete(self, request, pk):
        evidence = self._get_object(pk)
        if evidence is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        evidence.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
