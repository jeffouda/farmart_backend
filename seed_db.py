#!/usr/bin/env python3
"""Seed database with demo data for production"""

from app import create_app, db
from app.models import User, Farmer, Buyer, Animal, UserRole
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    print("🌱 Seeding database...")

    # Create Admin
    admin = User.query.filter_by(email="admin1@farmart.com").first()
    if not admin:
        admin = User(
            email="admin1@farmart.com",
            role=UserRole.ADMIN,  # Use uppercase enum value
            full_name="Admin User",
            is_active=True,
        )
        admin.set_password("admin1234")
        db.session.add(admin)
        print("✅ Admin created: admin1@farmart.com / admin1234")

    # Create Test Farmer
    farmer_user = User.query.filter_by(email="farmer@test.com").first()
    if not farmer_user:
        farmer_user = User(
            email="farmer@test.com",
            role=UserRole.FARMER,  # Use uppercase enum value
            full_name="John Kamau",
            phone_number="+254712345678",
            location="Nakuru",
            is_active=True,
        )
        farmer_user.set_password("farmer123")
        db.session.add(farmer_user)
        db.session.flush()

        farmer = Farmer(
            user_id=farmer_user.id,
            farm_name="Kamau Dairy Farm",
            location="Nakuru, Kenya",
            phone_number="+254712345678",
            is_verified=True,
        )
        db.session.add(farmer)
        db.session.flush()

        # Add livestock
        animals = [
            Animal(
                farmer_id=farmer.id,
                species="Cow",
                breed="Friesian",
                age=36,
                weight=450,
                price=85000,
                gender="female",
                health_history="Vaccinated, healthy",
                image_url=None,  # No image for seeded data
                status="available",
            ),
            Animal(
                farmer_id=farmer.id,
                species="Goat",
                breed="Boer",
                age=18,
                weight=45,
                price=15000,
                gender="male",
                health_history="Healthy, dewormed",
                image_url=None,  # No image for seeded data
                status="available",
            ),
            Animal(
                farmer_id=farmer.id,
                species="Sheep",
                breed="Dorper",
                age=24,
                weight=60,
                price=18000,
                gender="female",
                health_history="Excellent condition",
                image_url=None,  # No image for seeded data
                status="available",
            ),
        ]
        db.session.add_all(animals)
        print("✅ Farmer created: farmer@test.com / farmer123")
        print("✅ Added 3 livestock items")

    # Create Test Buyer
    buyer_user = User.query.filter_by(email="buyer@test.com").first()
    if not buyer_user:
        buyer_user = User(
            email="buyer@test.com",
            role=UserRole.BUYER,
            full_name="Mary Wanjiku",
            phone_number="+254723456789",
            location="Nairobi",
            is_active=True,
        )
        buyer_user.set_password("buyer123")
        db.session.add(buyer_user)
        db.session.flush()

        buyer = Buyer(
            user_id=buyer_user.id,
            delivery_address="Nairobi, Kenya",
            preferred_contact="phone",
        )
        db.session.add(buyer)
        print("✅ Buyer created: buyer@test.com / buyer123")

    db.session.commit()
    print("\n🎉 Database seeded successfully!")
    print("\n📋 Test Accounts:")
    print("   Admin:  admin1@farmart.com / admin1234")
    print("   Farmer: farmer@test.com / farmer123")
    print("   Buyer:  buyer@test.com / buyer123")
