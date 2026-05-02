import os
from dotenv import load_dotenv

load_dotenv()


def _get_db_url() -> str:
    url = os.getenv(
        'DATABASE_URL',
        'postgresql://postgres:postgres@localhost:5432/cbt_mock'
    )
    if url.startswith('postgres://'):
        url = url.replace('postgres://', 'postgresql://', 1)
    return url


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-change-in-production')
    SQLALCHEMY_DATABASE_URI = _get_db_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        'pool_recycle': 300,
        'connect_args': {'connect_timeout': 10},
    }

    # ── AI provider config ──────────────────────────────────────
    # Set AI_PROVIDER to: groq (default/free), gemini (free), openai (paid)
    AI_PROVIDER   = os.getenv('AI_PROVIDER', 'groq')
    GROQ_API_KEY  = os.getenv('GROQ_API_KEY', '')
    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

    # ── Admin credentials ───────────────────────────────────────
    ADMIN_USERNAME = os.getenv('ADMIN_USERNAME', 'admin')
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')

    # ── JWT ─────────────────────────────────────────────────────
    JWT_SECRET_KEY  = os.getenv('JWT_SECRET_KEY', 'jwt-dev-secret-change-in-production')
    JWT_EXPIRY_HOURS = int(os.getenv('JWT_EXPIRY_HOURS', '24'))

    # ── Upload ───────────────────────────────────────────────────
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')

    # ── CORS ─────────────────────────────────────────────────────
    CORS_ORIGINS = os.getenv('CORS_ORIGINS', '*')
