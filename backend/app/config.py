"""
RashtraBid Backend Configuration
Environment variables loaded from project root .env via env_loader.
"""
import os

from app.env_loader import get_mongo_db_name, get_mongo_uri

# MongoDB
MONGODB_URL = get_mongo_uri()
MONGODB_DB_NAME = get_mongo_db_name()
USE_REAL_MONGO = os.getenv("USE_REAL_MONGO", "0") == "1"

# Auth
JWT_SECRET = os.getenv("JWT_SECRET", "supersecretjwtkey_gemguard_2026")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

# Storage
STORAGE_PROVIDER = os.getenv("STORAGE_PROVIDER", "local")
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")

# AI
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# App
APP_ENV = os.getenv("APP_ENV", "development")
DEBUG = APP_ENV == "development"
