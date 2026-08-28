from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken


@api_view(['POST'])
def email_token_obtain_pair(request):
    """
    Custom endpoint to obtain JWT tokens using email and password instead of username.
    
    Request body:
    {
        "email": "admin@example.com",
        "password": "password123"
    }
    
    Response:
    {
        "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
        "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
    }
    """
    email = request.data.get('email')
    password = request.data.get('password')

    if not email or not password:
        return Response(
            {'detail': 'Email and password are required.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Look up user by email
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response(
            {'detail': 'Invalid credentials.'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    # Check password
    if not user.check_password(password):
        return Response(
            {'detail': 'Invalid credentials.'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    # Disabled users should not be able to log in
    if not user.is_active:
        return Response(
            {'detail': 'User account is disabled.'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    # Generate tokens with role and identity claims
    refresh = RefreshToken.for_user(user)
    access_token = refresh.access_token
    access_token['role'] = 'admin' if (user.is_staff or user.is_superuser) else 'assessor'
    access_token['first_name'] = user.first_name
    access_token['last_name'] = user.last_name
    access_token['is_staff'] = user.is_staff
    return Response(
        {
            'access': str(access_token),
            'refresh': str(refresh),
        },
        status=status.HTTP_200_OK
    )
