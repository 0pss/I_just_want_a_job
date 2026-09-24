import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-local-development-only")
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = [h.strip() for h in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_htmx",
    "tracker",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "jobtracker.urls"

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

WSGI_APPLICATION = "jobtracker.wsgi.application"
ASGI_APPLICATION = "jobtracker.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Europe/Berlin"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "tracker" / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

JOBTRACKER = {
    "ARBEITSAGENTUR_API_URL": "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs",
    "ARBEITSAGENTUR_API_KEY": "jobboerse-jobsuche",
    "JOBDETAIL_BASE_URL": "https://www.arbeitsagentur.de/jobsuche/jobdetail",
    "LLAMA_SERVER_URL": os.getenv("LLAMA_SERVER_URL", "http://127.0.0.1:8080"),
    "LLAMA_CPP_DIR": os.getenv("LLAMA_CPP_DIR", "~/Dokumente/Projekte/LocalLLM/llama.cpp"),
    "LLAMA_MODEL_PATH": os.getenv(
        "LLAMA_MODEL_PATH",
        "~/Dokumente/Projekte/LocalLLM/llama.cpp/models/Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
    ),
    "LLAMA_PORT": int(os.getenv("LLAMA_PORT", "8080")),
    "LLAMA_CONTEXT": int(os.getenv("LLAMA_CONTEXT", "4096")),
    "LLAMA_LOG_LEVEL": int(os.getenv("LLAMA_LOG_LEVEL", "2")),
    "LLAMA_READY_TIMEOUT": int(os.getenv("LLAMA_READY_TIMEOUT", "120")),
    "BUZZWORD_DIVERGENCE_THRESHOLD": float(os.getenv("BUZZWORD_DIVERGENCE_THRESHOLD", "3.0")),
    "IMAP_HOST": os.getenv("IMAP_HOST", ""),
    "IMAP_PORT": int(os.getenv("IMAP_PORT", "993")),
    "IMAP_USERNAME": os.getenv("IMAP_USERNAME", ""),
    "IMAP_PASSWORD": os.getenv("IMAP_PASSWORD", ""),
    "IMAP_MAILBOX": os.getenv("IMAP_MAILBOX", "INBOX"),
    "IMAP_SSL": os.getenv("IMAP_SSL", "1") == "1",
}

# Security settings are intentionally conservative for a local single-user app.
CSRF_TRUSTED_ORIGINS = []