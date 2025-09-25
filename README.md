# HFE Backend

A FastAPI-based backend for the Hope For Everybody (HFE) platform. It powers user management, provider/client workflows, case management, donations/payments, messaging, file management, and more for a community/nonprofit-focused application.

## 🚀 Features

- **FastAPI Framework**: High-performance, modern Python web framework
- **Multi-Role Support**: Admin, Users, Providers, Case Managers, Volunteers, and Donors
- **Authentication & Authorization**: JWT-based authentication with role-based access control
- **Database Integration**: SQLAlchemy ORM with PostgreSQL support
- **Background Tasks**: Celery integration with Redis for asynchronous task processing
- **Payment Processing**: Stripe integration for secure payment handling
- **File Management**: Support for avatars, documents, brochures, and attachments
- **Email Services**: SMTP integration for notifications and communications
- **Chat System**: Real-time messaging capabilities
- **Data Export**: Excel file generation and processing
- **Translation**: Multi-language support with Google Translate
- **Docker Support**: Containerized deployment ready

## 📋 Prerequisites

- Python 3.10 or higher
- PostgreSQL database
- Redis server (for Celery)
- Docker (optional, for containerized deployment)

## 🛠️ Installation

### Local Development Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd HFE_backend
   ```

2. **Create and activate virtual environment**
   ```bash
   python -m venv .venv
   
   # On Windows
   .venv\Scripts\activate
   
   # On macOS/Linux
   source .venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   # or
   make install
   ```

4. **Environment Configuration**
   - Copy `.env.example` to `.env` (if available)
   - Configure your environment variables in `.env`:
     ```env
     DATABASE_URL=postgresql://username:password@localhost:5432/hfe_db
     REDIS_URL=redis://localhost:6379/0
     SECRET_KEY=your-secret-key
     STRIPE_SECRET_KEY=your-stripe-secret-key
     SMTP_SERVER=your-smtp-server
     SMTP_PORT=587
     SMTP_USERNAME=your-email
     SMTP_PASSWORD=your-password
     ```

5. **Database Setup**
   ```bash
   # Run database migrations
   alembic upgrade head
   ```

6. **Start the application**
   ```bash
   # Development mode with auto-reload and Celery worker
   make run_local
   
   # Or manually
   uvicorn src.api.api:app --host 0.0.0.0 --port 8100 --reload
   ```

### Docker Deployment

1. **Build and run with Docker Compose**
   ```bash
   docker-compose up --build
   ```

2. **Or build Docker image manually**
   ```bash
   docker build -t hfe-backend .
   docker run -p 8100:8100 hfe-backend
   ```

## 📁 Project Structure

```
HFE_backend/
├── .env                                 # Environment variables (local), not committed contents
├── .git/
├── .github/
│   └── workflows/
│       └── master_ci.yml
├── .gitignore
├── .pre-commit-config.yaml
├── .venv/
├── Dockerfile
├── Makefile
├── README.md
├── VERSION
├── adbanner/                            # Ad banner images (many files; runtime uploads)
├── alembic/                             # DB migrations
│   ├── README
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
├── alembic.ini
├── attachments/                         # Generated/import files (samples, images, etc.)
├── avatars/                             # Pre-bundled avatar SVGs
│   
├── blog.db                               # Local SQLite database (dev/testing)
├── brochure/                             # PDF brochures (multiple files)
├── config_local.py
├── docker-compose.yml
├── hfe_images/                           # Uploaded images (many files; runtime uploads)
├── import_provider/                      # Import staging (empty by default)
├── pyproject.toml
├── requirements.txt
├── resume/                               # Uploaded resumes (PDFs)
├── scripts/
│   ├── clean_local_db.sh
│   ├── create_local_queue.sh
│   ├── create_test_queue.sh
│   ├── prepare_local_db.sh
│   └── prepare_test_db.sh
├── src/
│   ├── __init__.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── api.py                        # Main FastAPI app (mounted static paths, routers, health)
│   │   └── schemas.py                    # Pydantic schemas
│   ├── authentication/
│   │   ├── __init__.py
│   │   ├── JWTtoken.py
│   │   ├── auth_middleware.py
│   │   ├── encryption.py
│   │   ├── hashing.py
│   │   └── oauth2.py
│   ├── common/
│   │   ├── __init__.py
│   │   ├── admin                         # (empty marker folder)
│   │   ├── admins.py
│   │   ├── celery_worker.py              # Celery app entry: src.common.celery_worker.celery_app
│   │   ├── chat.py
│   │   ├── client.py
│   │   ├── constants.py
│   │   ├── donor.py
│   │   ├── dto.py
│   │   ├── email_service.py
│   │   ├── enums.py
│   │   ├── labels.py
│   │   ├── logger.py
│   │   ├── otp_service.py
│   │   ├── provider.py
│   │   ├── signup_document.py
│   │   ├── tasks.py
│   │   ├── translate.py
│   │   ├── user.py
│   │   ├── utils.py
│   │   ├── volunteer.py
│   │   └── welcome_email.html
│   ├── configs/
│   │   ├── __init__.py
│   │   ├── config.py                     # Settings, logger, etc.
│   │   └── database.py                   # SQLAlchemy engine/session
│   ├── models/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   └── users.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── admin.py
│   │   ├── casemanager.py
│   │   ├── chat.py
│   │   ├── client.py
│   │   ├── donor.py
│   │   ├── notification.py               # (currently empty)
│   │   ├── payment.py
│   │   ├── provider.py
│   │   ├── user.py
│   │   └── volunteer.py
│   ├── templates/
│   │   ├── activated.html
│   │   ├── chatranscript.html
│   │   ├── contactus.html
│   │   ├── paymentLink.html
│   │   ├── titaniumCreated.html
│   │   └── trialWelcome.html
│   └── tests/
│       ├── __init__.py
│       └── test_health.py
├── test_log.log                           # Application log (very large)
└── uploads/                               # Uploaded images (PNGs)
```

## 🔧 API Endpoints

The application provides the following main API groups:

### Authentication
- `POST /users/login` - User authentication
- `POST /users/register` - User registration
- `POST /users/forgot-password` - Password reset request
- `POST /users/reset-password` - Password reset confirmation

### User Management
- `GET /users/profile` - Get user profile
- `PUT /users/profile` - Update user profile
- `POST /users/avatar` - Upload user avatar

### Providers
- `GET /providers` - List providers
- `POST /providers` - Create provider profile
- `PUT /providers/{id}` - Update provider information

### Case Management
- `GET /cases` - List cases
- `POST /cases` - Create new case
- `PUT /cases/{id}` - Update case information

### Chat & Messaging
- `GET /chat/conversations` - Get user conversations
- `POST /chat/messages` - Send message
- `GET /chat/messages/{conversation_id}` - Get conversation messages

### Payments
- `POST /payments/create-intent` - Create payment intent
- `POST /payments/confirm` - Confirm payment
- `GET /payments/history` - Get payment history

### Volunteers
- `POST /volunteer/volunteer` - Self-register a volunteer (multipart/form-data)
- `GET /volunteer/all-volunteer` - List volunteers (filters: name, is_activated, user_id, zipcode, county, city, category, sort)
- `GET /volunteer/active-service-provider` - List active service providers visible to volunteers (filters supported)
- `PATCH /volunteer/update-volunteer/{uuid}` - Update volunteer profile (multipart/form-data)
- `DELETE /volunteer/delete-volunteer/{volunteer_uuid}` - Soft delete volunteer
- `GET /volunteer/{uuid}` - Get volunteer by UUID

### Donors
- `POST /donor/donor` - Self-register a donor (multipart/form-data)
- `GET /donor/all-donor` - List donors (filters: name, is_activated, user_id, zipcode, county, city, category, sort)
- `GET /donor/active-service-provider` - List active service providers visible to donors (filters supported)
- `PATCH /donor/update-donor/{uuid}` - Update donor profile (multipart/form-data)
- `DELETE /donor/delete-donor/{donor_uuid}` - Soft delete donor
- `GET /donor/{uuid}` - Get donor by UUID

### Admin Panel
- `GET /admin/users` - Manage users
- `GET /admin/providers` - Manage providers
- `GET /admin/analytics` - System analytics

## 🔒 Authentication

The application uses JWT (JSON Web Tokens) for authentication. Include the token in the Authorization header:

```
Authorization: Bearer <your-jwt-token>
```

## 🏃‍♂️ Running the Application

### Development Mode
```bash
make run_local
```
This starts both the FastAPI server and Celery worker for background tasks.

### Production Mode
```bash
make run
```
This runs the application with Gunicorn for production deployment.

### Health Check
The application includes a health check endpoint:
```
GET /health/
```

## 📊 Background Tasks

The application uses Celery for background task processing:

- Email notifications
- File processing
- Data exports
- Payment processing

Ensure Redis is running for Celery to function properly.

## 🧪 Testing

Run tests using pytest:
```bash
pytest src/tests/
```

## 📝 Code Quality

The project uses Ruff for code formatting and linting:

```bash
# Format code
ruff format .

# Check for linting issues
ruff check .
```

## 🚀 Deployment

### Environment Variables

Ensure the following environment variables are set in production:

- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `SECRET_KEY`: JWT secret key
- `STRIPE_SECRET_KEY`: Stripe API key
- `SMTP_*`: Email configuration

### Docker Deployment

The application is Docker-ready. Use the provided `Dockerfile` and `docker-compose.yml` for deployment.

## 📚 API Documentation

Once the application is running, you can access:

- **Swagger UI**: `http://localhost:8100/docs`
- **ReDoc**: `http://localhost:8100/redoc`

### Deployment availability
- Public site: https://hopeforeverybody.org/ — Volunteer and Donor modules are not yet deployed here.
- Company server (staging): http://45.248.33.189/dev_hfe/ — Volunteer and Donor modules are available here.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and linting
5. Submit a pull request

## 📄 License

[Add your license information here]

## 🆘 Support

For support and questions, please contact [your-contact-information].

---

**Version**: 0.1.0  
**Python**: 3.10+  
**Framework**: FastAPI 0.111.0
