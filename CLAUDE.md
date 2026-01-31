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

## Project Structure

```
QuickServeLegal/
├── src/
│   ├── main.py              # FastAPI application entry point
│   ├── config.py            # Configuration settings
│   ├── database.py          # Database connection and sessions
│   ├── auth.py              # Authentication logic
│   ├── documents.py         # Document upload/download logic
│   ├── notifications.py     # Email notification system
│   ├── pdf_generator.py     # Proof of Service PDF generation
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py          # User model
│   │   ├── document.py      # Document model
│   │   └── audit.py         # Audit log model
│   └── routes/
│       ├── __init__.py
│       ├── auth_routes.py   # Login, register, logout
│       ├── document_routes.py # Upload, download, list
│       └── dashboard_routes.py # User dashboard
├── templates/
│   ├── base.html            # Base template with layout
│   ├── index.html           # Landing page
│   ├── login.html           # Login page
│   ├── register.html        # Registration page
│   ├── dashboard.html       # User dashboard
│   ├── upload.html          # Document upload form
│   ├── download.html        # Document download page
│   └── components/
│       ├── navbar.html      # Navigation component
│       └── footer.html      # Footer component
├── static/
│   ├── css/
│   │   └── styles.css       # Custom styles (if needed)
│   ├── js/
│   │   └── app.js           # Minimal JavaScript (if needed)
│   └── logo.png             # QuickServe Legal logo
├── data/
│   ├── quickserve.db        # SQLite database (dev)
│   └── uploads/             # Uploaded documents (dev)
├── tests/
│   ├── test_auth.py
│   ├── test_documents.py
│   └── test_notifications.py
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variables template
├── .gitignore
├── CLAUDE.md                # This file
└── README.md
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

### Access the Application
- Local: http://localhost:8000
- API Docs: http://localhost:8000/docs

## Key Features (MVP)

1. **User Registration & Login**
   - Email + password authentication
   - Attorney verification (manual for MVP)
   - Terms of service acceptance

2. **Document Upload**
   - PDF upload only (MVP)
   - Select recipient by email
   - Add matter reference (optional)

3. **Notifications**
   - Email notification to recipient
   - Download link with secure token

4. **Document Download**
   - Secure, one-time tokenized link
   - Timestamp recorded on download
   - IP address logged

5. **Proof of Service**
   - Auto-generated PDF with:
     - Document details
     - Upload timestamp
     - Download timestamp
     - Recipient details
   - Available to uploader after download

6. **Audit Trail**
   - All actions logged
   - Immutable records
   - Exportable for court

## Legal Compliance

- **ECTA**: Electronic Communications and Transactions Act 25 of 2002
- **Rule 4A**: Uniform Rules of Court - electronic service of subsequent documents
- **POPIA**: Protection of Personal Information Act - data privacy

## Development Guidelines

- Follow existing patterns from the Brolink project where applicable
- Keep it simple - MVP first, enhance later
- Security is critical - this handles legal documents
- All timestamps in SAST (South African Standard Time)
- Mobile-responsive design (attorneys work from phones too)

## Environment Variables

See `.env.example` for required configuration:
- `SECRET_KEY`: Session encryption key
- `DATABASE_URL`: Database connection string
- `SMTP_*`: Email server configuration
- `UPLOAD_DIR`: Document storage directory
