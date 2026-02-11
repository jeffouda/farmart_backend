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

    # Polymorphic relationships
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
    phone_number = db.Column(db.String(20), unique=True, nullable=False)
    is_verified = db.Column(db.Boolean, default=False)
    wallet_balance = db.Column(db.Numeric(10, 2), default=0)

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
        return f"<Buyer {self.user_id}>"


class Animal(db.Model, TimestampMixin):
    __tablename__ = "animals"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
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
    buyer_id = db.Column(UUID(as_uuid=True), db.ForeignKey("buyers.id"), nullable=False)
    farmer_id = db.Column(UUID(as_uuid=True), db.ForeignKey("farmers.id"), nullable=False)
    bargain_id = db.Column(db.Integer, db.ForeignKey("bargain_sessions.id"), nullable=True)

    items = db.Column(db.JSON, nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending, held, completed, cancelled
    payment_status = db.Column(db.String(20), default="pending")
    payment_method = db.Column(db.String(50), default="mpesa")
    checkout_id = db.Column(db.String(100), nullable=True) # Linked to M-Pesa STK Push
    has_review = db.Column(db.Boolean, default=False)

    buyer = db.relationship("Buyer", backref="orders")
    farmer = db.relationship("Farmer", backref="orders")
    # Link to the detailed escrow tracking
    escrow = db.relationship("EscrowRecord", backref="order", uselist=False, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": str(self.id),
            "buyer_id": str(self.buyer_id),
            "farmer_id": str(self.farmer_id),
            "items": self.items,
            "total_amount": float(self.total_amount),
            "status": self.status,
            "payment_status": self.payment_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

class EscrowRecord(db.Model, TimestampMixin):
    __tablename__ = "escrow_records"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = db.Column(UUID(as_uuid=True), db.ForeignKey("orders.id"), nullable=False)
    
    # Using Numeric(10, 2) is best practice for currency to avoid floating-point errors
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    seller_phone = db.Column(db.String(20), nullable=False) # Essential for B2C payout
    
    # Statuses: pending (initial), held (paid by buyer), released (paid to farmer), 
    # disputed (hold on funds), refunded (returned to buyer)
    status = db.Column(db.String(20), default="pending") 
    
    # M-Pesa Tracking
    mpesa_receipt = db.Column(db.String(100), unique=True, nullable=True) # Unique receipt from STK callback
    b2c_conversation_id = db.Column(db.String(100), unique=True, nullable=True) # Links to the farmer payout result

    def __repr__(self):
        return f"<Escrow Order: {self.order_id} | Status: {self.status}>"

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

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": str(self.user_id),
            "animal_id": str(self.animal_id),
            "animal": self.animal.to_dict() if self.animal else None,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class BargainSession(db.Model, TimestampMixin):
    __tablename__ = "bargain_sessions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    animal_id = db.Column(UUID(as_uuid=True), db.ForeignKey("animals.id"), nullable=False)
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


class Dispute(db.Model, TimestampMixin):
    __tablename__ = "disputes"
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = db.Column(db.String(20), unique=True, nullable=False)
    
    # Link to order (if dispute is about an order)
    order_id = db.Column(UUID(as_uuid=True), db.ForeignKey("orders.id"), nullable=True)
    
    # Dispute parties
    filer_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    target_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=True)
    
    # Dispute details
    dispute_type = db.Column(db.String(20), default="order")  # 'order', 'user', 'livestock'
    reason = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    resolution = db.Column(db.String(20))  # 'refund', 'replacement', 'report'
    
    # Status
    status = db.Column(db.String(20), default="open")  # 'open', 'pending', 'resolved', 'dismissed'
    admin_notes = db.Column(db.Text, nullable=True)
    admin_decision = db.Column(db.String(20), nullable=True)  # 'refund_buyer', 'release_farmer', 'dismiss'
    
    # Farmer response fields
    farmer_response = db.Column(db.Text, nullable=True)
    farmer_response_at = db.Column(db.DateTime, nullable=True)
    farmer_evidence = db.Column(db.String(255), nullable=True)  # Path to uploaded evidence
    
    # Buyer response fields (when farmer files dispute)
    buyer_response = db.Column(db.Text, nullable=True)
    buyer_response_at = db.Column(db.DateTime, nullable=True)
    buyer_evidence = db.Column(db.String(255), nullable=True)
    
    # Relationships
    order = db.relationship("Order", backref="dispute")
    filer = db.relationship("User", foreign_keys=[filer_id], backref="disputes_filed")
    target = db.relationship("User", foreign_keys=[target_id], backref="disputes_against")
    
    def to_dict(self):
        return {
            "id": str(self.id),
            "ticket_id": self.ticket_id,
            "order_id": str(self.order_id) if self.order_id else None,
            "filer_id": str(self.filer_id),
            "target_id": str(self.target_id) if self.target_id else None,
            "dispute_type": self.dispute_type,
            "reason": self.reason,
            "description": self.description,
            "resolution": self.resolution,
            "status": self.status,
            "admin_notes": self.admin_notes,
            "admin_decision": self.admin_decision,
            "farmer_response": self.farmer_response,
            "farmer_response_at": self.farmer_response_at.isoformat() if self.farmer_response_at else None,
            "farmer_evidence": self.farmer_evidence,
            "buyer_response": self.buyer_response,
            "buyer_response_at": self.buyer_response_at.isoformat() if self.buyer_response_at else None,
            "buyer_evidence": self.buyer_evidence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class Message(db.Model):
    """
    Model for direct messages between users about livestock.
    Used by the negotiation API for messaging.
    """
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sender_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    receiver_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    livestock_id = db.Column(UUID(as_uuid=True), db.ForeignKey("animals.id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    sender = db.relationship("User", foreign_keys=[sender_id], backref="messages_sent")
    receiver = db.relationship("User", foreign_keys=[receiver_id], backref="messages_received")
    livestock = db.relationship("Animal", backref="messages")

    def to_dict(self):
        return {
            "id": self.id,
            "sender_id": str(self.sender_id),
            "receiver_id": str(self.receiver_id),
            "livestock_id": str(self.livestock_id),
            "content": self.content,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Notification(db.Model):
    """
    Model for user notifications (orders, negotiations, disputes)
    """
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(UUID(as_uuid=True), db.ForeignKey("users.id"), nullable=False)
    
    # Notification types
    type = db.Column(db.String(30), nullable=False)  # 'new_order', 'new_negotiation', 'new_dispute', 'order_update', 'negotiation_update'
    title = db.Column(db.String(100), nullable=False)
    message = db.Column(db.Text, nullable=False)
    
    # Related entity references
    related_id = db.Column(UUID(as_uuid=True), nullable=True)  # order_id, bargain_id, dispute_id
    related_type = db.Column(db.String(30), nullable=True)  # 'order', 'negotiation', 'dispute'
    
    # Status
    is_read = db.Column(db.Boolean, default=False)
    read_at = db.Column(db.DateTime, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", backref="notifications")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": str(self.user_id),
            "type": self.type,
            "title": self.title,
            "message": self.message,
            "related_id": str(self.related_id) if self.related_id else None,
            "related_type": self.related_type,
            "is_read": self.is_read,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


def create_notification(user_id, type, title, message, related_id=None, related_type=None):
    """Helper function to create a notification"""
    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        related_id=related_id,
        related_type=related_type
    )
    db.session.add(notification)
    db.session.commit()
    return notification
class PendingCheckout(db.Model, TimestampMixin):
    """
    Temporary storage for checkout data before payment is confirmed.
    Order is only created when M-Pesa callback confirms payment success.
    This prevents zombie orders on timeout/failure.
    """
    __tablename__ = "pending_checkouts"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)  # Same as temp_order_id
    buyer_id = db.Column(UUID(as_uuid=True), db.ForeignKey("buyers.id"), nullable=False)
    farmer_id = db.Column(UUID(as_uuid=True), db.ForeignKey("farmers.id"), nullable=False)
    bargain_id = db.Column(db.Integer, db.ForeignKey("bargain_sessions.id"), nullable=True)
    
    items = db.Column(db.JSON, nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    payment_method = db.Column(db.String(50), default="mpesa")
    checkout_id = db.Column(db.String(100), nullable=True)  # M-Pesa CheckoutRequestID
    
    # Status: pending, paid, expired, cancelled
    status = db.Column(db.String(20), default="pending")

    buyer = db.relationship("Buyer", backref="pending_checkouts")
    farmer = db.relationship("Farmer", backref="pending_checkouts")

    def __repr__(self):
        return f"<PendingCheckout {self.id} | Status: {self.status}>"
