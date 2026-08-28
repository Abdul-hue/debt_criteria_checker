import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


def env_bool(name, default=False):
    """
    Parse an env var as a bool, case-insensitively. A bare os.environ.get(...)
    == 'True' string match silently resolves to False for any variant the
    author didn't type exactly (e.g. EMAIL_USE_TLS=true), with no error or
    warning - so every boolean env var in this file goes through this instead.
    """
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ('true', '1', 'yes')


SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key')
DEBUG = env_bool('DEBUG', False)
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', '*').split(',')

TIME_ZONE = "Europe/London"
USE_TZ = True

# Shared secret for internal service-to-service calls from case assessment.
# Set via DEBT_CRITERIA_INTERNAL_KEY in .env — must match the key in the main project.
DEBT_CRITERIA_INTERNAL_KEY = os.environ.get('DEBT_CRITERIA_INTERNAL_KEY', '')

# Callers allowed to WRITE through the token-free /api/v1/criteria/internal/*
# endpoints (reads are open). Defaults to this server only — the CA backend runs
# here. Set INTERNAL_API_ALLOWED_IPS=* to allow writes from anywhere on the LAN.
INTERNAL_API_ALLOWED_IPS = [
    ip.strip() for ip in os.environ.get(
        'INTERNAL_API_ALLOWED_IPS', '127.0.0.1,::1,localhost'
    ).split(',') if ip.strip()
]

# Reverse proxies whose X-Forwarded-For header may be believed when deciding the
# caller IP above. Empty by default: this service is reached directly, so
# REMOTE_ADDR is the real client and a forwarded header would just be a caller
# claiming to be someone else. Only list a proxy that overwrites the header.
INTERNAL_API_TRUSTED_PROXIES = [
    ip.strip() for ip in os.environ.get('INTERNAL_API_TRUSTED_PROXIES', '').split(',')
    if ip.strip()
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt',
    'debt_app',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'debt_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'frontend' / 'dist'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'debt_project.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'data' / 'db.sqlite3',
    },
    'aryza': {
        'ENGINE': 'django.db.backends.mysql',
        'HOST': os.environ.get('ARYZA_DB_HOST'),
        'USER': os.environ.get('ARYZA_DB_USER'),
        'PASSWORD': os.environ.get('ARYZA_DB_PASSWORD'),
        'NAME': os.environ.get('ARYZA_DB_NAME'),
        'PORT': os.environ.get('ARYZA_DB_PORT', '3306'),
        'OPTIONS': {
            'connect_timeout': 10,
            'ssl': {'ssl-mode': 'REQUIRE'},
        },
    },
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

STATIC_URL = '/static/'
# collectstatic output. Kept out of the source tree (and out of git) - it is
# regenerated on every deploy by the collectstatic step in the Dockerfile.
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"

# Runtime log files (CRM vote sync, etc). Git-ignored; see logs/.gitkeep.
LOG_DIR = Path(os.environ.get('LOG_DIR') or (BASE_DIR / 'logs'))
LOG_DIR.mkdir(parents=True, exist_ok=True)

STATICFILES_DIRS = [
    BASE_DIR / 'frontend' / 'dist',
]

# WhiteNoise configuration
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'user': '1000/min',
        'assess': '1000/min',
    },
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# CORS Configuration
CORS_ALLOW_ALL_ORIGINS = True

# Security Headers for Non-HTTPS environments
SECURE_CROSS_ORIGIN_OPENER_POLICY = None
# Ensure cookies and sessions work on non-HTTPS if needed (though not used for JWT)
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=8),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': False,
    'UPDATE_LAST_LOGIN': True,
}

# Email configuration
EMAIL_HOST = os.environ.get('EMAIL_HOST', '')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', True)
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', '')

# MOC alert settings (Prompts 9-10)
MOC_ALERT_RECIPIENTS = [
    r for r in os.environ.get('MOC_ALERT_RECIPIENTS', '').split(',') if r
]
MOC_ALERT_FROM_EMAIL = os.environ.get('MOC_ALERT_FROM_EMAIL', '') or DEFAULT_FROM_EMAIL

# Request-tracing middleware. Off by default: it prints every request/response
# to stdout, which floods test output and production logs. Enable per-environment
# with REQUEST_DEBUG_MIDDLEWARE=true.
if env_bool('REQUEST_DEBUG_MIDDLEWARE', False):
    MIDDLEWARE.insert(0, 'debt_project.debug_middleware.RequestDebugMiddleware')
