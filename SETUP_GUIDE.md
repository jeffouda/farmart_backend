# FarmArt Backend Setup Guide

## Prerequisites

- **Python 3.9+**
- **PostgreSQL 13+**
- **pip** or **pipenv**

## Installation

### 1. Clone and Navigate
```bash
cd Farmart_backend
```

### 2. Install Dependencies

#### Using Pipenv (Recommended)
```bash
# Install pipenv if not installed
pip install pipenv

# Install all dependencies
pipenv install

# Activate virtual environment
pipenv shell
```

#### Using pip
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Database Setup

#### Create PostgreSQL Database
```sql
CREATE DATABASE farmart_db;
CREATE USER farmart_user WITH PASSWORD 'your_password_here';
GRANT ALL PRIVILEGES ON DATABASE farmart_db TO farmart_user;
```

#### Configure Environment Variables
Create a `.env` file in the `Farmart_backend` directory:

```env
# Database Configuration
DATABASE_URL=postgresql://farmart_user:your_password_here@localhost:5432/farmart_db

# JWT Configuration
JWT_SECRET_KEY=your-super-secret-jwt-key-change-in-production
JWT_ACCESS_TOKEN_EXPIRES=3600

# Flask Configuration
FLASK_APP=app.py
FLASK_ENV=development
SECRET_KEY=your-flask-secret-key

# Optional: Email Configuration
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
```

### 4. Initialize Database

```bash
# Run the database setup script
python manage_db.py db setup

# Or for development with seed data
python manage_db.py db migrate
```

### 5. Run the Application

```bash
# Development
python app.py

# Or with flask CLI
flask run --debug
```

The API will be available at `http://localhost:5000`

## Dependencies

### Core Dependencies (Pipfile)
```toml
[packages]
Flask = ">=2.3.0"
Flask-SQLAlchemy = ">=3.0.0"
Flask-Migrate = ">=4.0.0"
Flask-JWT-Extended = ">=4.5.0"
Flask-CORS = ">=4.0.0"
psycopg2-binary = ">=2.9.0"
python-dotenv = ">=1.0.0"
Werkzeug = ">=2.3.0"
email-validator = ">=2.0.0"
```

### Development Dependencies
```toml
[dev-packages]
pytest = ">=7.0.0"
pytest-flask = ">=1.2.0"
flake8 = ">=6.0.0"
black = ">=23.0.0"
```

## API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|---------|-------------|
| POST | `/api/auth/register` | Register new user |
| POST | `/api/auth/login` | Login and get JWT token |
| GET | `/api/auth/me` | Get current user |
| GET | `/api/auth/health` | Health check |

### Orders
| Method | Endpoint | Description |
|--------|---------|-------------|
| GET | `/api/orders/` | Get all orders for current user |
| POST | `/api/orders/` | Create new order |
| GET | `/api/orders/<id>` | Get specific order |
| PUT | `/api/orders/<id>` | Update order |
| POST | `/api/orders/<id>/confirm-receipt` | Confirm delivery (releases funds) |

### Reviews
| Method | Endpoint | Description |
|--------|---------|-------------|
| POST | `/api/reviews` | Create review |
| GET | `/api/reviews/farmer/<farmer_id>` | Get farmer reviews |

### Wishlist
| Method | Endpoint | Description |
|--------|---------|-------------|
| GET | `/api/wishlist/` | Get user wishlist |
| POST | `/api/wishlist/` | Add item to wishlist |
| DELETE | `/api/wishlist/<id>` | Remove from wishlist |

### Livestock
| Method | Endpoint | Description |
|--------|---------|-------------|
| GET | `/api/livestock/` | Get all livestock |
| GET | `/api/livestock/<id>` | Get specific animal |
| POST | `/api/livestock/` | Add new animal |
| PUT | `/api/livestock/<id>` | Update animal |
| DELETE | `/api/livestock/<id>` | Delete animal |

### Bargaining
| Method | Endpoint | Description |
|--------|---------|-------------|
| GET | `/api/bargain/` | Get bargain sessions |
| POST | `/api/bargain/` | Create bargain |
| GET | `/api/bargain/<id>` | Get bargain details |
| POST | `/api/bargain/<id>/message` | Send message |
| PUT | `/api/bargain/<id>/accept` | Accept offer |
| PUT | `/api/bargain/<id>/counter` | Counter offer |

### Disputes
| Method | Endpoint | Description |
|--------|---------|-------------|
| POST | `/api/disputes` | Create dispute |
| GET | `/api/disputes/` | Get user disputes |

## Testing

### Run Tests
```bash
pytest
```

### Create Test Database
```bash
# Tests use SQLite in-memory by default
pytest --cov=app
```

## Production Deployment

1. **Set production environment variables:**
   ```env
   FLASK_ENV=production
   DEBUG=False
   ```

2. **Use a production WSGI server:**
   ```bash
   gunicorn app:app -w 4 --bind 0.0.0.0:5000
   ```

3. **Set up reverse proxy (nginx) for SSL**

4. **Use PostgreSQL in production**

## Troubleshooting

### Common Issues

**ImportError: No module named '...'**
- Ensure virtual environment is activated
- Run `pip install -r requirements.txt`

**Connection refused to PostgreSQL**
- Verify PostgreSQL is running
- Check DATABASE_URL in .env
- Ensure database user has permissions

**JWT Token Errors**
- Check JWT_SECRET_KEY is set
- Ensure token hasn't expired
- Verify Authorization header format: `Bearer <token>`

### Reset Database
```bash
python manage_db.py db reset
```

### Seed Test Data
```bash
python manage_db.py seed
```

## File Structure
```
Farmart_backend/
├── app.py              # Application entry point
├── config.py           # Configuration classes
├── manage_db.py        # Database management CLI
├── Pipfile            # Dependencies (pipenv)
├── Pipfile.lock       # Locked dependencies
├── .env               # Environment variables (create this)
├── requirements.txt    # Dependencies (pip)
├── migrations/         # Flask-Migrate migrations
└── app/
    ├── __init__.py    # App factory
    ├── models.py      # SQLAlchemy models
    ├── auth/          # Authentication module
    ├── orders/        # Orders module
    ├── reviews/       # Reviews module
    ├── wishlist/      # Wishlist module
    ├── livestock/     # Livestock module
    ├── bargain/       # Bargaining module
    └── disputes/      # Disputes module
```
