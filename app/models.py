import uuid
from datetime import datetime
from enum import Enum
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import UUID
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


# Role Definitions using Enum for Type Safety
class UserRole(str, Enum):
    ADMIN = "admin"
    FARMER = "farmer"
    BUYER = "buyer"


# Base Mixin for Audit Trails
class TimestampMixin:
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class User(db.Model, TimestampMixin):
    __tablename__ = "users"

    # Using UUIDs for public-facing IDs
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.Enum(UserRole), nullable=False, default=UserRole.BUYER)
    is_active = db.Column(db.Boolean, default=True)

    # Polymorphic relationships to Farmer and Buyer
    farmer = db.relationship(
        "Farmer", backref="user", uselist=False, cascade="all, delete-orphan"
    )
    buyer = db.relationship(
        "Buyer", backref="user", uselist=False, cascade="all, delete-orphan"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email} | Role: {self.role}>"


class Farmer(db.Model, TimestampMixin):
    __tablename__ = "farmers"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)

    farm_name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(255), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)

    # Livestock relationship (Farmers own the animals)
    animals = db.relationship("Animal", backref="owner", lazy=True)

    def __repr__(self):
        return f"<Farmer {self.farm_name} | User: {self.user_id}>"


class Buyer(db.Model, TimestampMixin):
    __tablename__ = "buyers"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)

    delivery_address = db.Column(db.Text, nullable=True)
    preferred_contact = db.Column(db.String(50))

    def __repr__(self):
        return f"<Buyer {self.user_id} | Contact: {self.preferred_contact}>"


class Animal(db.Model, TimestampMixin):
    __tablename__ = "animals"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    farmer_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("farmers.id"), nullable=False
    )

    species = db.Column(db.String(50), nullable=False)  # e.g., Cow, Goat
    breed = db.Column(db.String(100))
    age = db.Column(db.Integer)  # months
    weight = db.Column(db.Float)  # kg
    price = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), default="available")  # available, reserved, sold

    image_url = db.Column(db.String(255))

    def __repr__(self):
        return f"<Animal {self.species} | {self.breed} | {self.status}>"
