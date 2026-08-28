"""Application records attached to an assessed case."""

from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from debt_app.models import Application

def _application_to_dict(app):
    return {
        "id": app.id,
        "aryza_reference": app.aryza_reference,
        "client_name": app.client_name,
        "created_at": app.created_at.isoformat(),
    }


class ApplicationListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 100)), 500)
        search = request.query_params.get('search', '')

        queryset = Application.objects.all().order_by('-created_at')
        if search:
            queryset = queryset.filter(
                Q(aryza_reference__icontains=search) | Q(client_name__icontains=search)
            )

        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": [_application_to_dict(a) for a in page_obj],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        required = ['aryza_reference', 'client_name']
        for field in required:
            if not data.get(field):
                return Response({"detail": f"{field} is required."}, status=status.HTTP_400_BAD_REQUEST)

        if Application.objects.filter(aryza_reference=data['aryza_reference']).exists():
            return Response({"detail": "An application with this aryza_reference already exists."}, status=status.HTTP_400_BAD_REQUEST)

        app = Application(
            aryza_reference=data['aryza_reference'],
            client_name=data['client_name'],
        )

        try:
            app.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        app.save()
        return Response(_application_to_dict(app), status=status.HTTP_201_CREATED)


class ApplicationDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def _get_object(self, pk):
        try:
            return Application.objects.get(id=pk)
        except Application.DoesNotExist:
            return None

    def get(self, request, pk):
        app = self._get_object(pk)
        if app is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_application_to_dict(app), status=status.HTTP_200_OK)

    def put(self, request, pk):
        app = self._get_object(pk)
        if app is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        for field in ['aryza_reference', 'client_name']:
            if field in request.data:
                setattr(app, field, request.data[field])

        try:
            app.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        app.save()
        return Response(_application_to_dict(app), status=status.HTTP_200_OK)

    def delete(self, request, pk):
        app = self._get_object(pk)
        if app is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        app.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
