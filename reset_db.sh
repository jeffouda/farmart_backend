#!/bin/bash

# Farmart Database Reset Script
# This script drops and recreates the database schema using Integer IDs

echo "🔄 Starting Database Reset..."

# 1. Drop and recreate the schema using postgres superuser
echo "📦 Dropping and recreating schema..."
sudo -u postgres psql -c "DROP DATABASE IF EXISTS farmart_db;"
sudo -u postgres psql -c "CREATE DATABASE farmart_db OWNER postgres;"
sudo -u postgres psql -d farmart_db -c "DROP SCHEMA IF EXISTS public CASCADE;"
sudo -u postgres psql -d farmart_db -c "CREATE SCHEMA public;"

# 2. Navigate to backend directory
cd /home/jeff/Farmart/Farmart_backend

# 3. Initialize Flask-Migrate if not already done
echo "📝 Initializing Flask-Migrate..."
export FLASK_APP=app.py
export FLASK_ENV=development
flask db init 2>/dev/null || echo "Flask-Migrate already initialized"

# 4. Generate new migration
echo "📋 Generating new migration..."
flask db migrate -m "Reset db to integers"

# 5. Apply the migration
echo "✅ Applying migration..."
flask db upgrade

# 6. Start the Flask server
echo "🚀 Starting Flask server..."
flask run --host 0.0.0.0 --port 5000

echo "✨ Database reset complete!"
