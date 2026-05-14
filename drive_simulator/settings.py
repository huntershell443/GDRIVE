

from pathlib import Path
import os
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / 'drive_simulator' / '.env')


SECRET_KEY = env('SECRET_KEY')




# Configurações de Email
#EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'  # Para desenvolvimento
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'  # Para produção

#Configurações SMTP (comente estas para desenvolvimento)
EMAIL_HOST = 'smtp.gmail.com'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = 'noreply@suaplatforma.com'

DEBUG = env.bool('DEBUG')

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['127.0.0.1', 'localhost'])

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'file_manager',
    'ai_assistant',
    'binary_analyzer.apps.BinaryAnalyzerConfig',
    'widget_tweaks',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Seu middleware customizado - ADICIONE ESTA LINHA
    'file_manager.middleware.ErrorHandlerMiddleware'

]

STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'


ROOT_URLCONF = 'drive_simulator.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.join(BASE_DIR, 'templates/'), 
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'ai_assistant.context_processors.ollama_settings',
            ],
        },
    },
]


# Channels/ASGI
ASGI_APPLICATION = 'drive_simulator.asgi.application'


# DB: Postgres em produção (DEBUG=False), SQLite em dev (DEBUG=True)
if DEBUG:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'cmbd.sqlite3',
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': env('POSTGRES_DB', default='gdrive'),
            'USER': env('POSTGRES_USER', default='gdrive'),
            'PASSWORD': env('POSTGRES_PASSWORD', default='gdrive'),
            'HOST': env('POSTGRES_HOST', default='db'),
            'PORT': env('POSTGRES_PORT', default='5432'),
            'CONN_MAX_AGE': env.int('POSTGRES_CONN_MAX_AGE', default=60),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]



LOGIN_URL = '/'

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

STATIC_URL = '/static/'

STATICFILES_DIRS = [
    os.path.join(BASE_DIR, 'static'),
]

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'



MEDIA_ROOT = os.environ.get("MEDIA_ROOT", str(BASE_DIR / 'gdrive_users'))
MEDIA_URL = '/media/'

# VirusTotal — apenas lookup por SHA-256 (nunca upload de arquivos).
# Coloque VT_API_KEY=sua_chave no .env para habilitar.
VT_API_KEY = env('VT_API_KEY', default='') or os.environ.get('VT_API_KEY', '')

# capa rules (opcional). Se quiser usar capa, baixe as regras e aponte o caminho.
# git clone https://github.com/mandiant/capa-rules
CAPA_RULES_PATH = env('CAPA_RULES_PATH', default='') or os.environ.get('CAPA_RULES_PATH', '')
if CAPA_RULES_PATH:
    os.environ['CAPA_RULES_PATH'] = CAPA_RULES_PATH

# Local LLM API (Ollama) endpoint
OLLAMA_API_URL = os.environ.get('OLLAMA_API_URL', 'http://localhost:11434/api/generate')
OLLAMA_DEFAULT_MODEL = os.environ.get('OLLAMA_DEFAULT_MODEL', 'llama3.2')
OLLAMA_API_KEY = os.environ.get('OLLAMA_API_KEY', '')
OLLAMA_SYSTEM_PROMPT = os.environ.get('OLLAMA_SYSTEM_PROMPT', '')

DATA_UPLOAD_MAX_MEMORY_SIZE = None  # sem limite no tamanho total do POST (exceto arquivos)
FILE_UPLOAD_MAX_MEMORY_SIZE = 0    # arquivos sempre gravados em disco (nunca em memória)

# Configurar diretório temporário personalizado
FILE_UPLOAD_TEMP_DIR = os.path.join(MEDIA_ROOT, 'temp_uploads')

# Criar diretório se não existir
import os
os.makedirs(FILE_UPLOAD_TEMP_DIR, exist_ok=True)

handler404 = 'file_manager.views.handler404'
handler500 = 'file_manager.views.handler500'

# CONFIGURACOES APACHE 


# Configurações para proxy reverso
USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Configurações de segurança para produção
CSRF_TRUSTED_ORIGINS = [
    'http://localhost',
    'http://drive.localhost',
    'https://localhost',
    'https://drive.localhost',
    'http://200.7.8.39',
    'https://200.7.8.39',
    'http://10.0.1.86',
    'https://10.0.1.86',
]

# Configurações de sessão e CSRF
SESSION_COOKIE_SECURE = False  # True se usar HTTPS real
CSRF_COOKIE_SECURE = False     # True se usar HTTPS real
