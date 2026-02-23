"""
Test script to verify notifications are working correctly.
Run this after placing an order to check if notifications were created.
"""

from app import create_app
from app.models import db, Notification, User, Farmer, Buyer

app = create_app()

with app.app_context():
    # Get all notifications
    notifications = (
        Notification.query.order_by(Notification.created_at.desc()).limit(20).all()
    )

    print("=" * 60)
    print("RECENT NOTIFICATIONS")
    print("=" * 60)

    if not notifications:
        print("No notifications found in database.")
    else:
        for n in notifications:
            user = User.query.get(n.user_id)
            print(f"\nID: {n.id}")
            print(f"Type: {n.type}")
            print(f"Title: {n.title}")
            print(f"Message: {n.message}")
            print(
                f"User: {user.email if user else 'Unknown'} (Role: {user.role if user else 'N/A'})"
            )
            print(f"Created: {n.created_at}")
            print(f"Is Read: {n.is_read}")
            print("-" * 40)

    print("\n" + "=" * 60)
    print("UNREAD COUNTS BY USER")
    print("=" * 60)

    users = User.query.all()
    for user in users:
        unread = Notification.query.filter_by(user_id=user.id, is_read=False).count()
        if unread > 0:
            print(f"{user.email} ({user.role}): {unread} unread")
