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

    # Profile fields
    full_name = db.Column(db.String(100), nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)
    location = db.Column(db.String(255), nullable=True)

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

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)

    farm_name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(255), nullable=False)
    phone_number = db.Column(db.String(20), unique=True, nullable=False)
    is_verified = db.Column(db.Boolean, default=False)

    # Livestock relationship (Farmers own the animals)
    animals = db.relationship("Animal", backref="owner", lazy=True)

    def __repr__(self):
        return f"<Farmer {self.farm_name} | User: {self.user_id}>"


class Buyer(db.Model, TimestampMixin):
    __tablename__ = "buyers"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)

    delivery_address = db.Column(db.Text, nullable=True)
    preferred_contact = db.Column(db.String(50))

    def __repr__(self):
        return f"<Buyer {self.user_id} | Contact: {self.preferred_contact}>"


class Animal(db.Model, TimestampMixin):
    __tablename__ = "animals"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    farmer_id = db.Column(db.Integer, db.ForeignKey("farmers.id"), nullable=False)

    species = db.Column(db.String(50), nullable=False)  # e.g., Cow, Goat
    breed = db.Column(db.String(100))
    age = db.Column(db.Integer)  # months
    weight = db.Column(db.Float)  # kg
    price = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), default="available")  # available, reserved, sold

    image_url = db.Column(db.String(255))

    def to_dict(self):
        return {
            "id": str(self.id),
            "species": self.species,
            "breed": self.breed,
            "age": self.age,
            "weight": self.weight,
            "price": float(self.price),
            "status": self.status,
            "image_url": self.image_url,
        }

    def __repr__(self):
        return f"<Animal {self.species} | {self.breed} | {self.status}>"


class Order(db.Model, TimestampMixin):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    buyer_id = db.Column(db.Integer, db.ForeignKey("buyers.id"), nullable=False)

    items = db.Column(db.JSON, nullable=False)  # List of {animal_id, name, price}
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending, paid, completed
    payment_method = db.Column(db.String(50), default="mpesa")  # mpesa, cod

    def to_dict(self):
        return {
            "id": str(self.id),
            "buyer_id": str(self.buyer_id),
            "items": self.items,
            "total_amount": float(self.total_amount),
            "status": self.status,
            "payment_method": self.payment_method,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<Order {self.id} | Buyer: {self.buyer_id} | ${self.total_amount}>"


class Wishlist(db.Model, TimestampMixin):
    __tablename__ = "wishlists"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    animal_id = db.Column(db.Integer, db.ForeignKey("animals.id"), nullable=False)

    # Relationship to Animal for eager loading
    animal = db.relationship("Animal", backref="wishlisted_by", lazy=True)

    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "animal_id": str(self.animal_id),
            # Include nested animal object
            "animal": self.animal.to_dict() if self.animal else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<Wishlist User: {self.user_id} | Animal: {self.animal_id}>"
