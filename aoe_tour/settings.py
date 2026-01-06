import logging
from pathlib import Path
from datetime import timedelta

import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

environ.Env.read_env(BASE_DIR / "app.env")
env = environ.Env()

SECRET_KEY = env("SECRET", cast=str, default="django-insecure-change-me")

DEBUG = env("DEBUG", cast=bool, default=False)

ALLOWED_HOSTS = env("ALLOWED_HOSTS", cast=list, default=[])
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS", cast=list, default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "django_celery_results",
    "django_celery_beat",
    "django_minio_backend",

    "common",
    "jwt_token",
    "user",
    "core",
    "aoe_world",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",

    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "aoe_tour.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "aoe_tour.wsgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL", default="sqlite:///db.sqlite3"),
}

AUTH_USER_MODEL = "user.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 6}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

JWT_SECRET_KEY = env("JWT_SECRET_KEY", cast=str, default=SECRET_KEY)
JWT_ALGORITHM = env("JWT_ALGORITHM", cast=str, default="HS256")
JWT_EXPIRATION_MINUTES = env("JWT_EXPIRATION_MINUTES", cast=int, default=90 * 24 * 60)
JWT_REFRESH_EXPIRATION_MINUTES = env("JWT_REFRESH_EXPIRATION_MINUTES", cast=int, default=60 * 24 * 365)
JWT_AUTH_HEADER_PREFIX = env("JWT_AUTH_HEADER_PREFIX", cast=str, default="Bearer")

MINIO_ENDPOINT = env("MINIO_ENDPOINT", default="localhost:9009")
MINIO_EXTERNAL_ENDPOINT = env("MINIO_EXTERNAL_ENDPOINT", default=MINIO_ENDPOINT)
MINIO_EXTERNAL_ENDPOINT_USE_HTTPS = env("MINIO_EXTERNAL_ENDPOINT_USE_HTTPS", cast=bool, default=False)
MINIO_ACCESS_KEY = env("MINIO_ACCESS_KEY", default="minio")
MINIO_SECRET_KEY = env("MINIO_SECRET_KEY", default="minio123")
MINIO_USE_HTTPS = env("MINIO_USE_HTTPS", cast=bool, default=False)

MINIO_PRIVATE_BUCKET = env("MINIO_PRIVATE_BUCKET", default="private")
MINIO_PUBLIC_BUCKET = env("MINIO_PUBLIC_BUCKET", default="public")
MINIO_MEDIA_FILES_BUCKET = env("MINIO_MEDIA_FILES_BUCKET", default=MINIO_PRIVATE_BUCKET)
MINIO_STATIC_FILES_BUCKET = env("MINIO_STATIC_FILES_BUCKET", default=MINIO_PUBLIC_BUCKET)

MINIO_URL_EXPIRY_HOURS = timedelta(hours=env("MINIO_URL_EXPIRY_HOURS", cast=int, default=24))
MINIO_CONSISTENCY_CHECK_ON_START = env("MINIO_CONSISTENCY_CHECK_ON_START", cast=bool, default=False)
MINIO_BUCKET_CHECK_ON_SAVE = env("MINIO_BUCKET_CHECK_ON_SAVE", cast=bool, default=True)

STORAGES = {
    "default": {
        "BACKEND": "django_minio_backend.models.MinioBackend",
        "OPTIONS": {
            "MINIO_ENDPOINT": MINIO_ENDPOINT,
            "MINIO_EXTERNAL_ENDPOINT": MINIO_EXTERNAL_ENDPOINT,
            "MINIO_EXTERNAL_ENDPOINT_USE_HTTPS": MINIO_EXTERNAL_ENDPOINT_USE_HTTPS,
            "MINIO_ACCESS_KEY": MINIO_ACCESS_KEY,
            "MINIO_SECRET_KEY": MINIO_SECRET_KEY,
            "MINIO_USE_HTTPS": MINIO_USE_HTTPS,

            "MINIO_PRIVATE_BUCKETS": [MINIO_PRIVATE_BUCKET],
            "MINIO_PUBLIC_BUCKETS": [MINIO_PUBLIC_BUCKET],
            "MINIO_DEFAULT_BUCKET": MINIO_MEDIA_FILES_BUCKET,

            "MINIO_URL_EXPIRY_HOURS": MINIO_URL_EXPIRY_HOURS,
            "MINIO_CONSISTENCY_CHECK_ON_START": MINIO_CONSISTENCY_CHECK_ON_START,
            "MINIO_BUCKET_CHECK_ON_SAVE": MINIO_BUCKET_CHECK_ON_SAVE,
        },
    },

    "staticfiles": {
        "BACKEND": "django_minio_backend.models.MinioBackendStatic",
        "OPTIONS": {
            "MINIO_ENDPOINT": MINIO_ENDPOINT,
            "MINIO_EXTERNAL_ENDPOINT": MINIO_EXTERNAL_ENDPOINT,
            "MINIO_EXTERNAL_ENDPOINT_USE_HTTPS": MINIO_EXTERNAL_ENDPOINT_USE_HTTPS,
            "MINIO_ACCESS_KEY": MINIO_ACCESS_KEY,
            "MINIO_SECRET_KEY": MINIO_SECRET_KEY,
            "MINIO_USE_HTTPS": MINIO_USE_HTTPS,

            "MINIO_PUBLIC_BUCKETS": [MINIO_PUBLIC_BUCKET],
            "MINIO_DEFAULT_BUCKET": MINIO_STATIC_FILES_BUCKET,
            "MINIO_URL_EXPIRY_HOURS": MINIO_URL_EXPIRY_HOURS,
            "MINIO_CONSISTENCY_CHECK_ON_START": MINIO_CONSISTENCY_CHECK_ON_START,
            "MINIO_BUCKET_CHECK_ON_SAVE": MINIO_BUCKET_CHECK_ON_SAVE,
        },
    },
}

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"

LANGUAGE_CODE = env("LANGUAGE_CODE", default="en-us")
TIME_ZONE = env("TIME_ZONE", default="Asia/Tehran")
USE_I18N = env("USE_I18N", cast=bool, default=True)
USE_TZ = env("USE_TZ", cast=bool, default=True)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CORS_ALLOW_ALL_ORIGINS = env("CORS_ALLOW_ALL_ORIGINS", cast=bool, default=False)
CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS", cast=list, default=[])

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = "django-db"
CELERY_TASK_ALWAYS_EAGER = env("CELERY_TASK_ALWAYS_EAGER", cast=bool, default=False)
CELERY_TASK_EAGER_PROPAGATES = env("CELERY_TASK_EAGER_PROPAGATES", cast=bool, default=False)
CELERY_TASK_TRACK_STARTED = True
CELERY_ENABLE_UTC = False
CELERY_TIMEZONE = TIME_ZONE
CELERY_WORKER_CONCURRENCY = env("CELERY_WORKER_CONCURRENCY", cast=int, default=4)
CELERY_WORKER_PREFETCH_MULTIPLIER = env("CELERY_WORKER_PREFETCH_MULTIPLIER", cast=int, default=1)

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "jwt_token.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "EXCEPTION_HANDLER": "common.handlers.api_exception_handler",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "AOE Tour API",
    "DESCRIPTION": "API for aoe_tour",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "APPEND_COMPONENTS": {
        "securitySchemes": {
            "ApiKeyAuth": {
                "type": "apiKey",
                "in": "header",
                "name": "Authorization",
                "description": "Bearer <access_token>",
            }
        }
    },
    "SECURITY": [{"ApiKeyAuth": []}],
    "COMPONENT_SPLIT_REQUEST": True,
}

sentry_sdk.init(
    dsn=env('SENTRY_DSN', cast=str, default=''),
    integrations=[
        DjangoIntegration(), 
        CeleryIntegration(),
        LoggingIntegration(
            level=logging.INFO,
            event_level=logging.WARNING,
        ),
    ],
    environment=env('SENTRY_ENV', cast=str, default='development'),
    enable_tracing=True,
    attach_stacktrace=True,
    send_default_pii=False,
    traces_sample_rate=env.float('SENTRY_TRACES_SAMPLE_RATE', default=1.0),
    profiles_sample_rate=env.float('SENTRY_PROFILES_SAMPLE_RATE', default=1.0),
)