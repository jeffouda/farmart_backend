#!/bin/bash
# Production Deployment Script for Farmart

echo "🚀 Farmart Production Deployment"
echo "================================="

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ ERROR: .env file not found!"
    echo "   Copy .env.example to .env and configure it"
    exit 1
fi

# Install dependencies
echo "📦 Installing dependencies..."
pip install -r requirements.txt

# Run database migrations
echo "🗄️  Running database migrations..."
flask db upgrade

# Seed database (optional - comment out for production)
echo "🌱 Seeding database with demo data..."
python seed_db.py

# Test database connection
echo "🔍 Testing database connection..."
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.session.execute(db.text('SELECT 1')); print('✅ Database connected')"

# Create uploads directory
echo "📁 Creating uploads directory..."
mkdir -p app/static/uploads

echo ""
echo "✅ Deployment preparation complete!"
echo ""
echo "🎯 Next Steps:"
echo "   1. Configure your .env file with production values"
echo "   2. Set up PostgreSQL database"
echo "   3. Configure Cloudinary for image uploads"
echo "   4. Run: gunicorn app:app -w 4 --bind 0.0.0.0:5000"
echo ""
echo "📋 Test Accounts (if seeded):"
echo "   Admin:  admin@farmart.com / admin123"
echo "   Farmer: farmer@test.com / farmer123"
echo "   Buyer:  buyer@test.com / buyer123"
