"""
QuickServe Legal - Configuration Settings
"""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import model_validator
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    APP_NAME: str = "QuickServe Legal"
    APP_DESCRIPTION: str = "Electronic service of legal documents with verified receipt"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Security
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    DOWNLOAD_TOKEN_EXPIRE_HOURS: int = 72  # 3 days

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/quickserve.db"

    # File Storage
    UPLOAD_DIR: Path = Path("./data/uploads")
    MAX_FILE_SIZE_MB: int = 25  # Maximum upload size in MB
    ALLOWED_EXTENSIONS: set = {".pdf"}  # MVP: PDF only

    # Email (SMTP)
    SMTP_HOST: str = "smtp.gmail.com"  # Change for production
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: str = "noreply@quickservelegal.co.za"
    SMTP_FROM_NAME: str = "QuickServe Legal"

    # URLs
    BASE_URL: str = "http://localhost:8000"  # Change for production

    # Business Rules
    REMINDER_AFTER_HOURS: int = 24  # Send reminder after 24 hours
    DEEMED_SERVED_AFTER_HOURS: int = 72  # Deemed served after 72 hours
    DOCUMENT_RETENTION_DAYS: int = 365 * 7  # 7 years retention

    # Timezone
    TIMEZONE: str = "Africa/Johannesburg"  # SAST

    # LAWTrust AES Integration
    LAWTRUST_API_URL: str = "https://api.lawtrust.co.za/aes/v1"
    LAWTRUST_API_KEY: Optional[str] = None
    LAWTRUST_API_SECRET: Optional[str] = None
    LAWTRUST_MOCK_MODE: bool = True  # Use mock signing in development

    # AES Signing Settings
    AES_REQUIRED_FOR_SERVICE: bool = True  # Require AES signature before serving
    AES_CERTIFICATE_VALIDITY_DAYS: int = 365  # Default validity for mock certificates

    # SendGrid Email Delivery Tracking
    SENDGRID_API_KEY: Optional[str] = None  # Set in .env for production
    SENDGRID_WEBHOOK_SECRET: Optional[str] = None  # For verifying webhook signatures
    EMAIL_PROVIDER: str = "smtp"  # "smtp" for development, "sendgrid" for production
    EMAIL_TRACKING_ENABLED: bool = True  # Track delivery, opens, clicks
    EMAIL_OPEN_TRACKING: bool = True  # Track email opens (tracking pixel)
    EMAIL_CLICK_TRACKING: bool = True  # Track link clicks

    # PNSA Branch Integration
    PNSA_ENABLED: bool = False  # Enable PNSA branch portal
    PNSA_SERVICE_FEE: str = "50.00"  # Service fee in ZAR (stored as string for Decimal)
    PNSA_SESSION_EXPIRE_MINUTES: int = 480  # 8 hours for branch operators

    # OCR / Document Extraction (Claude Vision)
    OCR_ENABLED: bool = False  # Enable OCR document extraction
    ANTHROPIC_API_KEY: Optional[str] = None  # Claude API key for OCR
    OCR_MAX_PAGES: int = 3  # Maximum pages to process for OCR
    OCR_CONFIDENCE_THRESHOLD: float = 0.7  # Minimum confidence for auto-fill

    @model_validator(mode="after")
    def validate_secret_key(self):
        """Refuse to start with the default secret key in production."""
        if not self.DEBUG and self.SECRET_KEY == "dev-secret-key-change-in-production":
            raise ValueError(
                "SECRET_KEY must be changed from the default value in production. "
                "Set a strong, unique SECRET_KEY in your .env file."
            )
        return self

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# Create settings instance
settings = Settings()

# Ensure upload directory exists
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
TEMPLATES_DIR = PROJECT_ROOT / "templates"
STATIC_DIR = PROJECT_ROOT / "static"
DATA_DIR = PROJECT_ROOT / "data"
