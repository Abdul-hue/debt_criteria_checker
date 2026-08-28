"""User administration endpoints."""

from django.contrib.auth.models import User
from django.db.models import Q
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

def _user_to_dict(user):
    dept = None
    try:
        profile = user.profile
        if profile.department_id:
            dept = {'id': profile.department.id, 'name': profile.department.name}
    except Exception:
        pass
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_staff": user.is_staff,
        "role": 'admin' if user.is_staff else 'assessor',
        "is_active": user.is_active,
        "date_joined": user.date_joined.isoformat(),
        "department": dept,
    }


class UserListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def get(self, request):
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 100)), 500)
        search = request.query_params.get('search', '')

        queryset = User.objects.select_related('profile__department').all().order_by('username')
        if search:
            queryset = queryset.filter(
                Q(username__icontains=search) |
                Q(email__icontains=search) |
                Q(first_name__icontains=search) |
                Q(last_name__icontains=search)
            )

        from django.core.paginator import Paginator
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(page)

        return Response({
            "count": paginator.count,
            "next": f"{request.build_absolute_uri(request.path)}?page={page + 1}" if page_obj.has_next() else None,
            "previous": f"{request.build_absolute_uri(request.path)}?page={page - 1}" if page_obj.has_previous() else None,
            "results": [_user_to_dict(u) for u in page_obj],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        data = request.data
        required = ['username', 'email', 'password']
        for field in required:
            if not data.get(field):
                return Response({"detail": f"{field} is required."}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(username=data['username']).exists():
            return Response({"detail": "A user with this username already exists."}, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=data['email']).exists():
            return Response({"detail": "A user with this email already exists."}, status=status.HTTP_400_BAD_REQUEST)

        user = User(
            username=data['username'],
            email=data['email'],
            first_name=data.get('first_name', ''),
            last_name=data.get('last_name', ''),
            is_staff=data.get('is_staff', False),
            is_active=data.get('is_active', True),
        )
        user.set_password(data['password'])

        try:
            user.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        user.save()
        return Response(_user_to_dict(user), status=status.HTTP_201_CREATED)


class UserDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAdminUser]

    def _get_object(self, pk):
        try:
            return User.objects.get(id=pk)
        except User.DoesNotExist:
            return None

    def get(self, request, pk):
        user = self._get_object(pk)
        if user is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_user_to_dict(user), status=status.HTTP_200_OK)

    def put(self, request, pk):
        user = self._get_object(pk)
        if user is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        for field in ['username', 'email', 'first_name', 'last_name', 'is_staff', 'is_active']:
            if field in request.data:
                setattr(user, field, request.data[field])

        if 'password' in request.data and request.data['password']:
            user.set_password(request.data['password'])

        try:
            user.full_clean()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        user.save()
        return Response(_user_to_dict(user), status=status.HTTP_200_OK)

    def delete(self, request, pk):
        user = self._get_object(pk)
        if user is None:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        # Prevent self-deletion
        if user == request.user:
            return Response({"detail": "You cannot delete your own account."}, status=status.HTTP_400_BAD_REQUEST)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
