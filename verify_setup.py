"""
Verification script for the Farmart backend environment.
Tests database connectivity and creates a test user.
"""

import sys
import os

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text
from app import create_app
from app.models import db, User, Farmer, Buyer, UserRole


def verify_environment():
    """Verify the development environment is set up correctly."""
    print("=" * 60)
    print("Farmart Backend Environment Verification")
    print("=" * 60)

    # Create the Flask app
    app = create_app()

    with app.app_context():
        try:
            # Test database connection
            print("\n[1] Testing database connection...")
            result = db.session.execute(text("SELECT 1"))
            print("    ✓ Database connection successful")

            # Create a test user
            print("\n[2] Creating test user...")
            test_email = "test@farmart.dev"

            # Check if user already exists
            existing_user = User.query.filter_by(email=test_email).first()
            if existing_user:
                print(f"    ✓ Test user already exists: {test_email}")
            else:
                test_user = User(email=test_email, role=UserRole.BUYER, is_active=True)
                test_user.set_password("testpassword123")
                db.session.add(test_user)
                db.session.commit()
                print(f"    ✓ Test user created: {test_email}")

            # Verify tables exist
            print("\n[3] Verifying database tables...")
            tables = ["users", "farmers", "buyers", "animals"]
            for table in tables:
                result = db.session.execute(
                    text(
                        f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{table}')"
                    )
                )
                if result.scalar():
                    print(f"    ✓ Table '{table}' exists")
                else:
                    print(f"    ✗ Table '{table}' not found")
                    return False

            # Verify that User, Farmer, Buyer classes can be imported
            print("\n[4] Verifying model imports...")
            print(f"    ✓ User class: {User}")
            print(f"    ✓ Farmer class: {Farmer}")
            print(f"    ✓ Buyer class: {Buyer}")

            print("\n" + "=" * 60)
            print("Environment verified and ready for Auth development.")
            print("=" * 60)
            return True

        except Exception as e:
            print(f"\n✗ Error during verification: {str(e)}")
            import traceback

            traceback.print_exc()
            return False
        finally:
            db.session.close()


if __name__ == "__main__":
    success = verify_environment()
    sys.exit(0 if success else 1)
