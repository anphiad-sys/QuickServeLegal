# QuickServe Legal

Electronic service of legal documents with verified receipt confirmation.

## Project Overview

QuickServe Legal is a web-based platform for South African attorneys to serve legal documents electronically with automatic proof of receipt. When a recipient downloads a document, the system generates a verified proof of service.

### Core Value Proposition
- **For uploading attorneys**: Instant delivery, verified receipt, complete audit trail
- **For receiving attorneys**: Convenient access, organised documents, clear records
- **Key differentiator**: Proof of actual download (not just "sent"), unlike competitors

## Tech Stack

- **Backend**: Python 3.11+ with FastAPI
- **Frontend**: HTML + Tailwind CSS + HTMX (minimal JavaScript)
- **Database**: SQLite (development) → PostgreSQL (production)
- **File Storage**: Local (development) → AWS S3 (production)
- **PDF Generation**: ReportLab (for Proof of Service documents)
- **Email**: SMTP (development) → SendGrid (production)
- **Authentication**: Session-based with secure cookies
- **OCR**: Claude Vision API for document extraction
- **Digital Signatures**: LAWTrust AES integration (mock in development)

## Project Structure

```
QuickServeLegal/
├── src/
│   ├── main.py              # FastAPI app entry point (lifespan-based startup)
│   ├── config.py            # Configuration settings (Pydantic)
│   ├── database.py          # Async SQLAlchemy connection and sessions
│   ├── auth.py              # Authentication (password hashing, sessions)
│   ├── documents.py         # Document upload/download (streaming, atomic)
│   ├── notifications.py     # Email notification system
│   ├── pdf_generator.py     # Proof of Service / Court Filing PDF generation
│   ├── audit.py             # Immutable audit logging with hash-chain
│   ├── email_tracking.py    # SendGrid webhook delivery tracking
│   ├── ocr_processor.py     # OCR document extraction with XSS sanitization
│   ├── pnsa_auth.py         # PNSA branch operator authentication
│   ├── signatures.py        # LAWTrust AES digital signatures
│   ├── certificate_manager.py # Digital certificate management
│   ├── billing.py           # Walk-in service fee tracking
│   ├── csrf.py              # Double-submit cookie CSRF protection
│   ├── rate_limit.py        # In-memory sliding window rate limiting
│   ├── timestamps.py        # SAST timezone utilities (now_utc, to_sast)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py          # User model
│   │   ├── document.py      # Document model
│   │   ├── audit.py         # Audit log model (hash-chain)
│   │   ├── signature.py     # Digital signature model
│   │   ├── certificate.py   # LAWTrust certificate model
│   │   ├── branch.py        # PNSA branch model
│   │   ├── branch_operator.py # Branch operator model
│   │   └── walk_in_service.py # Walk-in service model
│   └── routes/
│       ├── __init__.py
│       ├── auth_routes.py   # Login, register, logout (with email validation)
│       ├── document_routes.py # Upload, download, list
│       ├── audit_routes.py  # Audit trail viewing/export
│       ├── certificate_routes.py # Certificate management
│       ├── signing_routes.py # AES document signing
│       ├── webhook_routes.py # SendGrid webhook handlers
│       └── pnsa_routes.py   # PNSA branch portal (scan, review, serve)
├── templates/
│   ├── base.html            # Base template with layout
│   ├── index.html           # Landing page
│   ├── login.html           # Login page
│   ├── register.html        # Registration page
│   ├── dashboard.html       # User dashboard
│   ├── documents.html       # Documents list
│   ├── document_detail.html # Document detail view
│   ├── upload.html          # Document upload form
│   ├── upload_success.html  # Upload success page
│   ├── download.html        # Document download page
│   ├── download_error.html  # Download error page
│   ├── certificates.html    # Certificates list
│   ├── certificate_detail.html
│   ├── signing.html         # Document signing page
│   ├── audit_trail.html     # Audit trail view
│   ├── audit_verify.html    # Audit verification
│   └── pnsa/               # PNSA branch operator templates
│       ├── base.html
│       ├── login.html
│       ├── dashboard.html
│       ├── document_review.html
│       ├── scan.html
│       ├── messenger_form.html
│       └── print_confirmation.html
├── static/
│   └── css/
│       └── styles.css       # Custom styles
├── data/
│   ├── quickserve.db        # SQLite database (dev)
│   └── uploads/             # Uploaded documents (dev)
├── tests/
│   ├── conftest.py          # Pytest fixtures (async DB, client, test user)
│   ├── test_auth.py         # Authentication tests (23 tests)
│   ├── test_documents.py    # Document flow tests (20 tests)
│   ├── test_security.py     # CSRF, rate limiting, secret key tests (12 tests)
│   ├── test_important_issues.py # Code review fixes (18 tests)
│   ├── test_minor_issues.py # Deprecation checks (4 tests)
│   └── test_sanity.py       # DB/client smoke tests (2 tests)
├── requirements.txt         # Python dependencies
├── pytest.ini               # Pytest configuration (asyncio auto mode)
├── .env.example             # Environment variables template
├── .gitignore
└── CLAUDE.md                # This file
```

## Running the Application

### Development Setup
```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows

# Install dependencies
python -m pip install -r requirements.txt

# Run the development server
python -m uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### Running Tests
```bash
python -m pytest tests/ -v
```

### Access the Application
- Local: http://localhost:8000
- API Docs: http://localhost:8000/docs

## Key Features

1. **User Registration & Login**
   - Email + password authentication with email validation
   - CSRF protection (double-submit cookie)
   - Rate limiting on auth endpoints
   - Attorney verification (manual for MVP)

2. **Document Upload & Service**
   - PDF upload with streaming size validation
   - Secure tokenized download links
   - Atomic download marking (prevents race conditions)
   - Email notification to recipient

3. **Proof of Service**
   - Auto-generated court-ready PDF with SAST timestamps
   - Document details, upload/download timestamps, recipient details
   - Available to uploader after download

4. **Digital Signatures (AES)**
   - LAWTrust AES integration for digital signing
   - Certificate management with expiry tracking
   - Court Filing Certificate generation

5. **Audit Trail**
   - Immutable hash-chain audit log
   - All actions logged with IP address
   - Chain integrity verification
   - Exportable for court

6. **PNSA Branch Portal**
   - Walk-in document service for branch operators
   - OCR document extraction (Claude Vision API)
   - Document scanning, review, and service workflow
   - Billing/fee tracking

## Security Architecture

- **CSRF**: Double-submit cookie pattern on all POST forms
- **Rate Limiting**: In-memory sliding window, per IP+path
- **Password Hashing**: SHA-256 with unique salts (consolidated in auth.py)
- **Session Tokens**: Signed with itsdangerous (URLSafeTimedSerializer)
- **File Upload**: Streaming chunked reads, early size rejection
- **XSS Prevention**: Jinja2 autoescaping + OCR input sanitization
- **Audit Integrity**: SHA-256 hash chain, tamper detection
- **Webhook Security**: SendGrid signature verification (reject when no secret)

## Timestamps

- **Database**: All timestamps stored as naive UTC
- **Display/Legal**: SAST (South African Standard Time, UTC+2)
- **Helper**: Use `now_utc()` from `src/timestamps.py` instead of `datetime.utcnow()`
- **Conversion**: Use `format_sast()` / `to_sast()` for display

## Legal Compliance

- **ECTA**: Electronic Communications and Transactions Act 25 of 2002
- **Rule 4A**: Uniform Rules of Court - electronic service of subsequent documents
- **POPIA**: Protection of Personal Information Act - data privacy

## Development Guidelines

- Security is critical - this handles legal documents
- All timestamps use `now_utc()` from `src/timestamps.py` (never `datetime.utcnow()`)
- Use `python -m pip install` (pip is not installed standalone)
- Mobile-responsive design (attorneys work from phones too)

## Environment Variables

See `.env.example` for required configuration:
- `SECRET_KEY`: Session encryption key (must be changed from default in production)
- `DATABASE_URL`: Database connection string
- `SMTP_*`: Email server configuration
- `UPLOAD_DIR`: Document storage directory
- `SENDGRID_WEBHOOK_SECRET`: Webhook verification secret
