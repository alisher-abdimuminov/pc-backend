from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

BASE_DIR = Path(__file__).resolve().parent.parent


SECRET_KEY = config("SECRET_KEY", cast=str)

DEBUG = config("DEBUG", cast=bool)

ALLOWED_HOSTS = config("ALLOWED_HOSTS", cast=Csv())


# Application definition

INSTALLED_APPS = [
	"unfold",
	"django.contrib.admin",
	"django.contrib.auth",
	"django.contrib.contenttypes",
	"django.contrib.sessions",
	"django.contrib.messages",
	"django.contrib.staticfiles",
	# extra
	"corsheaders",
	"rest_framework",
	"rest_framework_simplejwt",
	# local
	"users",
	"attendance",
	"assignments",
]

AUTH_USER_MODEL = "users.User"

MIDDLEWARE = [
	"django.middleware.security.SecurityMiddleware",
	"django.contrib.sessions.middleware.SessionMiddleware",
	"corsheaders.middleware.CorsMiddleware",
	"django.middleware.common.CommonMiddleware",
	"django.middleware.csrf.CsrfViewMiddleware",
	"django.contrib.auth.middleware.AuthenticationMiddleware",
	"users.audit.AuditContextMiddleware",
	"django.contrib.messages.middleware.MessageMiddleware",
	"django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
	{
		"BACKEND": "django.template.backends.django.DjangoTemplates",
		"DIRS": [],
		"APP_DIRS": True,
		"OPTIONS": {
			"context_processors": [
				"django.template.context_processors.request",
				"django.contrib.auth.context_processors.auth",
				"django.contrib.messages.context_processors.messages",
			],
		},
	},
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

DB_ENGINE = config("DB_ENGINE", default="sqlite3", cast=str)

if DB_ENGINE == "postgresql":
	DATABASES = {
		"default": {
			"ENGINE": "django.db.backends.postgresql",
			"NAME": config("DB_NAME", cast=str),
			"USER": config("DB_USER", cast=str),
			"PASSWORD": config("DB_PASSWORD", cast=str),
			"HOST": config("DB_HOST", default="localhost", cast=str),
			"PORT": config("DB_PORT", default=5432, cast=int),
		}
	}
else:
	DATABASES = {
		"default": {
			"ENGINE": "django.db.backends.sqlite3",
			"NAME": BASE_DIR / "db.sqlite3",
		}
	}


# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = []


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = "uz"

TIME_ZONE = "Asia/Tashkent"

USE_I18N = True

USE_TZ = True


# static files
STATIC_URL = "static/"
STATIC_ROOT = "static"

# media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# cors
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", cast=Csv())

# csrf
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", cast=Csv())
CSRF_COOKIE_SECURE = True

# hemis
HEMIS = {
	"REST_API": config("HEMIS_REST_API", cast=str),
	"STUDENT_LOGIN": config("HEMIS_STUDENT_LOGIN", cast=str),
	"STUDENT_ME": config("HEMIS_STUDENT_ME", cast=str),
	"TEACHER_LOGIN": config("HEMIS_TEACHER_LOGIN", cast=str),
	"TEACHER_ME": config("HEMIS_TEACHER_ME", cast=str),
}

HEMIS_GROUPS_TOKEN = config("HEMIS_GROUPS_TOKEN")

# rest framework
REST_FRAMEWORK = {
	"DEFAULT_AUTHENTICATION_CLASSES": (
		"rest_framework_simplejwt.authentication.JWTAuthentication",
	),
	"DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
	"DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
	"PAGE_SIZE": 50,
}

SIMPLE_JWT = {
	"ACCESS_TOKEN_LIFETIME": timedelta(hours=12),
	"REFRESH_TOKEN_LIFETIME": timedelta(days=30),
	"UPDATE_LAST_LOGIN": True,
}

# attendance
ATTENDANCE = {
	# GPS aniqligi (metr) shu qiymatdan katta bo'lsa attempt rad etiladi
	"MAX_LOCATION_ACCURACY": config(
		"ATTENDANCE_MAX_LOCATION_ACCURACY", default=100, cast=int
	),
	# deepface sozlamalari
	"FACE_MODEL": config("ATTENDANCE_FACE_MODEL", default="ArcFace", cast=str),
	"FACE_DETECTOR": config("ATTENDANCE_FACE_DETECTOR", default="retinaface", cast=str),
	"FACE_DISTANCE_METRIC": "cosine",
	"FACE_ANTI_SPOOFING": config(
		"ATTENDANCE_FACE_ANTI_SPOOFING", default=True, cast=bool
	),
}

# unfold
UNFOLD = {
	"SITE_TITLE": "PC",
	"SITE_HEADER": "PC - Amaliyot nazorati",
}

# Email
# https://docs.djangoproject.com/en/6.1/topics/email/#topic-email-configuration

MAILERS = {
	"default": {
		"BACKEND": "django.core.mail.backends.console.EmailBackend",
	},
}
