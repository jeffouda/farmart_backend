#!/usr/bin/env python3
"""
Farmart Database Nuclear Reset Script
=====================================
Usage: python manage_db.py

This script:
1. Drops all tables from the database
2. Recreates all tables based on current models.py (Integer PKs)
3. Seeds test data (user, farmer, animal)
"""

import sys
import os

# Add the backend directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.models import db, User, Farmer, Animal, Buyer, UserRole
import uuid

def reset_database():
    """Nuclear reset of the database."""

    print("🚀 Starting Database Nuclear Reset...")

    # Create app with development config
    app = create_app("development")

    # OVERRIDE: Manually setting the URI with the encoded password 'H@40960.ness'
    # We use %40 because @ is a reserved character in URLs.
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:Happyness@localhost:5432/farmart_db'

    with app.app_context():
        try:
            # Step 1: Drop all tables
            print("💥 Dropping all tables...")
            db.drop_all()
            print("✅ All tables dropped.")

            # Step 2: Recreate all tables
            print("🔨 Recreating tables from models.py...")
            db.create_all()
            print("✅ All tables created with Integer PKs.")

            # Step 3: Seed test data
            print("🌱 Seeding test data...")
            seed_test_data()

            print("\n✨ Database wiped and rebuilt successfully!")
            print("\nTest credentials:")
            print("  Email: test@farmart.com")
            print("  Password: testpass123")
            
        except Exception as e:
            print(f"\n❌ Error during reset: {e}")

def seed_test_data():
    """Seed the database with test data."""

    # Create a test user (buyer)
    test_user = User(
        email="test@farmart.com",
        full_name="Test Buyer",
        phone_number="+254700000000",
        location="Nairobi",
    )
    test_user.set_password("testpass123")
    db.session.add(test_user)
    db.session.flush()  # Get the user ID

    # Create buyer profile
    buyer = Buyer(
        user_id=test_user.id,
        delivery_address="123 Test Street, Nairobi",
        preferred_contact="email",
    )
    db.session.add(buyer)
    db.session.flush()

    # Create a test farmer user
    farmer_user = User(
        email="farmer@farmart.com",
        full_name="John Kamau",
        phone_number="+254711111111",
        location="Nakuru",
        role=UserRole.FARMER,
    )
    farmer_user.set_password("farmerpass123")
    db.session.add(farmer_user)
    db.session.flush()

    # Create farmer profile
    farmer = Farmer(
        user_id=farmer_user.id,
        farm_name="Kamau's Farm",
        location="Nakuru",
        phone_number="+254711111111",
        is_verified=True,
    )
    db.session.add(farmer)
    db.session.flush()

    # Create test animals
    animals = [
        Animal(
            farmer_id=farmer.id,
            species="Cow",
            breed="Boran",
            age=36,  # 3 years
            weight=450,
            price=185000,
            status="available",
            image_url="https://images.unsplash.com/photo-1546445317-29f4545e9d53?auto=format&fit=crop&q=80",
        ),
        Animal(
            farmer_id=farmer.id,
            species="Goat",
            breed="Boer",
            age=18,  # 1.5 years
            weight=35,
            price=28000,
            status="available",
            image_url="https://images.unsplash.com/photo-1484557985045-edf25e08da73?auto=format&fit=crop&q=80",
        ),
        Animal(
            farmer_id=farmer.id,
            species="Sheep",
            breed="Dorper",
            age=12,  # 1 year
            weight=45,
            price=32000,
            status="available",
            image_url="https://images.unsplash.com/photo-1484557985045-edf25e08da73?auto=format&fit=crop&q=80",

        ),
    ]
    db.session.add_all(animals)
    db.session.commit()