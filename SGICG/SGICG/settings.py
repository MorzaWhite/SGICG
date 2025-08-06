# SGICG/settings.py

from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-+d8$em)2duguy4qyze)tfn_oa16ng@*81fx$ljd3@emwb&4p4%'
DEBUG = True
ALLOWED_HOSTS = []

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'certificacion',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'SGICG.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'SGICG.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'es-co'
TIME_ZONE = 'America/Bogota'
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# --------------------------------------------------------------------------
# --- CONFIGURACIÓN DE ARCHIVOS (MODO LOCAL SIMPLIFICADO) ---
# --------------------------------------------------------------------------

# 1. Archivos Estáticos (CSS, JS) y Plantillas Excel
STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
PLANTILLAS_ROOT = BASE_DIR / 'plantillas'

# 2. Archivos de Usuario (Excels, QRs, Fotos)
# URL para acceder a las imágenes desde el navegador
MEDIA_URL = '/media/'
# RUTA FÍSICA: La ubicación REAL en tu disco duro donde se guardarán las carpetas.
MEDIA_ROOT = r'C:\Users\Usuario\Desktop\ordenes'

# ¡HEMOS ELIMINADO MEDIA_ROOT_UNC y ORDENES_ROOT PORQUE NO SON NECESARIOS EN MODO LOCAL!

# 3. Tiempos de Etapa
TIEMPOS_ETAPA = {
    'INGRESO': 8,
    'FOTOGRAFIA': 4,
    'REVISION': 24,
    'IMPRESION': 2,
}