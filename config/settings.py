from pathlib import Path

from decouple import Csv, config
from django.utils.timezone import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent


SECRET_KEY = config("SECRET_KEY")

DEBUG = config("DEBUG", cast=bool)

ALLOWED_HOSTS = config("ALLOWED_HOSTS", cast=Csv())


INSTALLED_APPS = [
	"unfold",
	"unfold.contrib.filters",
	"django.contrib.admin",
	"django.contrib.auth",
	"django.contrib.contenttypes",
	"django.contrib.sessions",
	"django.contrib.messages",
	"django.contrib.staticfiles",
	# external
	"rest_framework",
	# local
	"users",
	"attendance",
	"assignments",
	"reports",
]

MIDDLEWARE = [
	"django.middleware.security.SecurityMiddleware",
	# cors
	"corsheaders.middleware.CorsMiddleware",
	"django.contrib.sessions.middleware.SessionMiddleware",
	"django.middleware.common.CommonMiddleware",
	"django.middleware.csrf.CsrfViewMiddleware",
	"django.contrib.auth.middleware.AuthenticationMiddleware",
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

ENV = config("ENV", default="dev")
DATABASES = {
	"default": {
		"ENGINE": "django.db.backends.sqlite3",
		"NAME": BASE_DIR / "db.sqlite3",
	}
	if ENV == "dev"
	else {
		"ENGINE": "django.db.backends.postgresql",
		"NAME": config("POSTGRES_DB", default="pc"),
		"USER": config("POSTGRES_USER", default="pc"),
		"PASSWORD": config("POSTGRES_PASSWORD", default="pc"),
		"HOST": config("POSTGRES_HOST", default="127.0.0.1"),
		"PORT": config("POSTGRES_PORT", default="5432"),
	},
}

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = []


LANGUAGE_CODE = "en-us"

TIME_ZONE = "Asia/Tashkent"

USE_I18N = True

USE_TZ = True


# static files
STATIC_URL = "static/"
STATIC_ROOT = "static"

# media files
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


MAILERS = {
	"default": {
		"BACKEND": "django.core.mail.backends.console.EmailBackend",
	},
}

REST_FRAMEWORK = {
	"DEFAULT_AUTHENTICATION_CLASSES": (
		"rest_framework_simplejwt.authentication.JWTAuthentication",
	),
	"DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
	"DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
	"PAGE_SIZE": 50,
}
SIMPLE_JWT = {
	"ACCESS_TOKEN_LIFETIME": timedelta(hours=8),
	"REFRESH_TOKEN_LIFETIME": timedelta(days=30),
	"ROTATE_REFRESH_TOKENS": True,
	"BLACKLIST_AFTER_ROTATION": False,
}

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [
	"https://pc.samdpi.uz",
	"https://api.pc.samdpi.uz",
]

CSRF_TRUSTED_ORIGINS = [
	"https://api.pc.uzfi.uz",
	"https://api.pc.samdpi.uz",
	"http://localhost:8000",
]

CSRF_COOKIE_SECURE = True

HEMIS = {
	"CLIENT_ID": config("HEMIS_CLIENT_ID"),
	"CLIENT_SECRET": config("HEMIS_CLIENT_SECRET"),
	"REDIRECT_URI": config("HEMIS_REDIRECT_URI"),
	"STUDENT_AUTHORIZE_URL": config("HEMIS_STUDENT_AUTHORIZE_URL"),
	"STUDENT_ACCESS_TOKEN_URL": config("HEMIS_STUDENT_ACCESS_TOKEN_URL"),
	"STUDENT_RESOURCE_OWNER_URL": config("HEMIS_STUDENT_RESOURCE_OWNER_URL"),
	"TEACHER_AUTHORIZE_URL": config("HEMIS_TEACHER_AUTHORIZE_URL"),
	"TEACHER_ACCESS_TOKEN_URL": config("HEMIS_TEACHER_ACCESS_TOKEN_URL"),
	"TEACHER_RESOURCE_OWNER_URL": config("HEMIS_TEACHER_RESOURCE_OWNER_URL"),
	"IMAGE_ALLOWED_HOSTS": config("HEMIS_IMAGE_ALLOWED_HOSTS"),
}

HEMIS_GROUPS_TOKEN = config("HEMIS_GROUPS_TOKEN")

HEMIS_GROUPS_URL = "https://student.samdpi.uz/rest/v1/data/group-list"

ATTENDANCE_SHIFTS = {
	1: {
		1: {
			"start": "08:00",
			"end": "10:00",
		},
		2: {
			"start": "10:00",
			"end": "12:00",
		},
		3: {
			"start": "12:00",
			"end": "14:00",
		},
	},
	2: {
		1: {
			"start": "12:00",
			"end": "14:00",
		},
		2: {
			"start": "14:00",
			"end": "16:00",
		},
		3: {
			"start": "16:00",
			"end": "18:00",
		},
	},
}

FACE_VERIFY = {
	"MODEL_NAME": config("FACE_MODEL_NAME", default="ArcFace"),
	"DETECTOR_BACKEND": config("FACE_DETECTOR_BACKEND", default="retinaface"),
	"DISTANCE_METRIC": config("FACE_DISTANCE_METRIC", default="cosine"),
	"ANTI_SPOOFING": config("FACE_ANTI_SPOOFING", cast=bool),
}

MAX_HEMIS_IMAGE_BYTES = config(
	"MAX_HEMIS_IMAGE_BYTES", default=8 * 1024 * 1024, cast=int
)
MAX_ATTENDANCE_IMAGE_BYTES = config(
	"MAX_ATTENDANCE_IMAGE_BYTES", default=8 * 1024 * 1024, cast=int
)
MAX_ASSIGNMENT_FILE_BYTES = config(
	"MAX_ASSIGNMENT_FILE_BYTES", default=30 * 1024 * 1024, cast=int
)
