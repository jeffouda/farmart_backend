# Farmart Backend Setup Guide

## Prerequisites

- Python 3.8+
- PostgreSQL 12+
- pip or pipenv

## Installation Steps

### 1. Clone the Repository
```bash
git clone https://github.com/jeffouda/farmart_frontend.git
cd Farmart/Farmart_backend
```

### 2. Install Dependencies
Using pipenv (recommended):
```bash
pip install pipenv
pipenv install
```

Or using pip:
```bash
pip install -r requirements.txt
```

### 3. Set Up PostgreSQL Database

#### Option A: Using psql command line
```bash
sudo -u postgres psql
```

In PostgreSQL shell:
```sql
CREATE DATABASE farmart_db;
CREATE USER postgres WITH PASSWORD 'farmart';
ALTER ROLE postgres SUPERUSER;
GRANT ALL PRIVILEGES ON DATABASE farmart_db TO postgres;
\q
```

#### Option B: Using createdb command
```bash
createdb farmart_db -U postgres -W
# Password: farmart
```

### 4. Configure Environment Variables

Copy the `.env` file (already configured):
```bash
# The .env file should contain:
DATABASE_URL=postgresql://postgres:farmart@localhost:5432/farmart_db
JWT_SECRET_KEY=super-secret-permanent-key-123
FLASK_APP=app.py
FLASK_ENV=development
```

### 5. Initialize Database
```bash
# Run migrations
pipenv run flask db upgrade

# Or if using pip
flask db upgrade
```

### 6. Start the Server
```bash
# Development mode
pipenv run flask run

# Or
flask run
```

The server will start at `http://localhost:5000`

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register new user
- `POST /api/auth/login` - Login user
- `GET /api/auth/me` - Get current user info

## Troubleshooting

### Database Connection Error
Ensure PostgreSQL is running:
```bash
# Linux (systemd)
sudo systemctl start postgresql

# macOS
brew services start postgresql

# Windows
net start postgresql
```

### Port Already in Use
```bash
# Kill process on port 5000
lsof -ti:5000 | xargs kill -9
```

### Reset Database
```bash
flask db downgrade
flask db upgrade
```

## Development Notes

- The backend runs on `http://localhost:5000`
- CORS is enabled for all origins (configure in production)
- JWT tokens expire in 1 hour (configurable via `JWT_ACCESS_TOKEN_EXPIRES`)
