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

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.Enum(UserRole), nullable=False, default=UserRole.BUYER)
    is_active = db.Column(db.Boolean, default=True)

    # Profile fields
    full_name = db.Column(db.String(100), nullable=True)
    phone_number = db.Column(db.String(20), nullable=True)
    location = db.Column(db.String(255), nullable=True)

    # Reputation fields (for farmers)
    average_rating = db.Column(db.Float, default=0.0)
    review_count = db.Column(db.Integer, default=0)

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

    # Changed to UUID to match your existing DB state
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)

    farm_name = db.Column(db.String(100), nullable=False)
    location = db.Column(db.String(255), nullable=False)
    phone_number = db.Column(db.String(20), unique=True, nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    wallet_balance = db.Column(db.Numeric(10, 2), default=0)

    # Livestock relationship
    animals = db.relationship("Animal", backref="owner", lazy=True)

    def __repr__(self):
        return f"<Farmer {self.farm_name} | User: {self.user_id}>"


class Buyer(db.Model, TimestampMixin):
    __tablename__ = "buyers"

    # Changed to UUID to match your existing DB state
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)

    delivery_address = db.Column(db.Text, nullable=True)
    preferred_contact = db.Column(db.String(50))

    def __repr__(self):
        return f"<Buyer {self.user_id} | Contact: {self.preferred_contact}>"


class Animal(db.Model, TimestampMixin):
    __tablename__ = "animals"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Farmer ID is now a UUID
    farmer_id = db.Column(UUID(as_uuid=True), db.ForeignKey("farmers.id"), nullable=False)

    species = db.Column(db.String(50), nullable=False)
    breed = db.Column(db.String(100))
    age = db.Column(db.Integer)
    weight = db.Column(db.Float)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), default="available")
    gender = db.Column(db.String(20))
    health_history = db.Column(db.Text)
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
            "gender": self.gender,
            "health_history": self.health_history,
            "image_url": self.image_url,
            "farmer_name": self.owner.farm_name if self.owner else None,
            "farmer_id": str(self.owner.id) if self.owner else None,
            "location": self.owner.location if self.owner else None,
        }


class Order(db.Model, TimestampMixin):
    __tablename__ = "orders"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Buyer and Farmer are now UUIDs
    buyer_id = db.Column(UUID(as_uuid=True), db.ForeignKey("buyers.id"), nullable=False)
    farmer_id = db.Column(UUID(as_uuid=True), db.ForeignKey("farmers.id"), nullable=False)
    bargain_id = db.Column(db.Integer, db.ForeignKey("bargain_sessions.id"), nullable=True)

    items = db.Column(db.JSON, nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), default="pending")
    payment_status = db.Column(db.String(20), default="pending")
    payment_method = db.Column(db.String(50), default="mpesa")
    has_review = db.Column(db.Boolean, default=False)

    buyer = db.relationship("Buyer", backref="orders")
    farmer = db.relationship("Farmer", backref="orders")

    def to_dict(self):
        return {
            "id": str(self.id),
            "buyer_id": str(self.buyer_id),
            "farmer_id": str(self.farmer_id),
            "items": self.items,
            "total_amount": float(self.total_amount),
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Review(db.Model, TimestampMixin):
    __tablename__ = "reviews"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = db.Column(UUID(as_uuid=True), db.ForeignKey("orders.id"), nullable=False)
    reviewer_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    target_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)

    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    tags = db.Column(db.JSON, nullable=True)

    order = db.relationship("Order", backref="review")
    reviewer = db.relationship("User", foreign_keys=[reviewer_id], backref="reviews_given")
    target = db.relationship("User", foreign_keys=[target_id], backref="reviews_received")


class Wishlist(db.Model, TimestampMixin):
    __tablename__ = "wishlists"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    animal_id = db.Column(UUID(as_uuid=True), db.ForeignKey("animals.id"), nullable=False)

    animal = db.relationship("Animal", backref="wishlisted_by", lazy=True)


class BargainSession(db.Model, TimestampMixin):
    __tablename__ = "bargain_sessions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    animal_id = db.Column(UUID(as_uuid=True), db.ForeignKey("animals.id"), nullable=False)
    # Corrected to UUID to match Buyer and Farmer
    buyer_id = db.Column(UUID(as_uuid=True), db.ForeignKey("buyers.id"), nullable=False)
    farmer_id = db.Column(UUID(as_uuid=True), db.ForeignKey("farmers.id"), nullable=False)

    initial_offer = db.Column(db.Numeric(10, 2), nullable=False)
    final_price = db.Column(db.Numeric(10, 2), nullable=True)
    status = db.Column(db.String(20), default="pending")
    expires_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    animal = db.relationship("Animal", backref="bargain_sessions")
    buyer = db.relationship("Buyer", backref="bargain_sessions")
    farmer = db.relationship("Farmer", backref="bargain_sessions")
    messages = db.relationship("BargainMessage", backref="session", lazy="dynamic")

    def to_dict(self, include_messages=True):
        from app.models import Order
        linked_order = Order.query.filter_by(bargain_id=self.id).first()
        return {
            "id": str(self.id),
            "animal_id": str(self.animal_id),
            "buyer_id": str(self.buyer_id),
            "status": self.status,
            "order_id": str(linked_order.id) if linked_order else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class BargainMessage(db.Model):
    __tablename__ = "bargain_messages"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.Integer, db.ForeignKey("bargain_sessions.id"), nullable=False)
    sender_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    sender_role = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=False)
    offered_price = db.Column(db.Numeric(10, 2), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": str(self.id),
            "session_id": str(self.session_id),
            "message": self.message,
            "created_at": self.created_at.isoformat()
        }