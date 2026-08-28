"""The caller's own department."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from debt_app.helpers import get_user_department

class MyDepartmentView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        dept = get_user_department(request.user)
        if dept is None:
            return Response({"department": None}, status=status.HTTP_200_OK)
        return Response({
            "department": {
                "id": dept.id,
                "name": dept.name,
                "slug": dept.slug,
                "description": dept.description,
            }
        }, status=status.HTTP_200_OK)
