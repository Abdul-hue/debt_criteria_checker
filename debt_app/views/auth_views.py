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

    print(f"[AUTH DEBUG] Attempting login for email: '{email}'")
    print(f"[AUTH DEBUG] Password provided length: {len(password) if password else 0}")
    if password:
        print(f"[AUTH DEBUG] Password provided (FIRST 3): {password[:3]}...")

    if not email or not password:
        print("[AUTH DEBUG] Missing email or password")
        return Response(
            {'detail': 'Email and password are required.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Look up user by email
        user = User.objects.get(email=email)
        print(f"[AUTH DEBUG] Found user: {user.username}")
    except User.DoesNotExist:
        print(f"[AUTH DEBUG] User not found for email: {email}")
        return Response(
            {'detail': 'Invalid credentials.'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    # Check password
    if not user.check_password(password):
        print(f"[AUTH DEBUG] Password check failed for user: {user.username}")
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

    # Generate tokens with role claim
    refresh = RefreshToken.for_user(user)
    access_token = refresh.access_token
    access_token['role'] = 'admin' if (user.is_staff or user.is_superuser) else 'assessor'
    return Response(
        {
            'access': str(access_token),
            'refresh': str(refresh),
        },
        status=status.HTTP_200_OK
    )
