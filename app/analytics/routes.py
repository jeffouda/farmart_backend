from flask import jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
import uuid
from datetime import datetime, timedelta
from sqlalchemy import func
from app.models import db, User, Farmer, Animal, Order, Review, Buyer
from . import analytics_bp


@analytics_bp.route("/farmer", methods=["GET"])
@jwt_required()
def get_farmer_analytics():
    """
    Get analytics data for farmer dashboard.
    Returns:
    - Total revenue
    - Total orders
    - Average order value
    - Customer rating
    - Revenue by month (chart data)
    - Recent activity
    """
    current_user_id_str = get_jwt_identity()

    user = User.query.filter_by(id=current_user_id_str).first()
    
    # Convert enum to string for comparison
    user_role = user.role.value if hasattr(user.role, 'value') else str(user.role)
    user_role_lower = user_role.lower() if user_role else user_role
    
    if not user or user_role_lower != "farmer":
        return jsonify({"error": "Only farmers can view analytics"}), 403

    farmer = Farmer.query.filter_by(user_id=current_user_id_str).first()
    if not farmer:
        return jsonify({"error": "Farmer profile not found"}), 404

    # Get all completed orders for this farmer
    completed_orders = Order.query.filter_by(
        farmer_id=farmer.id, 
        status="delivered"
    ).all()

    # Calculate basic stats
    total_revenue = sum(float(o.total_amount) for o in completed_orders)
    total_orders = len(completed_orders)
    avg_order_value = total_revenue / total_orders if total_orders > 0 else 0

    # Get customer rating from reviews
    user_reviews = Review.query.filter_by(target_id=current_user_id_str).all()
    avg_rating = sum(r.rating for r in user_reviews) / len(user_reviews) if user_reviews else 0
    review_count = len(user_reviews)

    # Get pending orders count
    pending_orders = Order.query.filter_by(
        farmer_id=farmer.id,
        status="pending"
    ).count()

    # Get active listings count
    active_listings = Animal.query.filter_by(
        farmer_id=farmer.id,
        status="available"
    ).count()

    # Get monthly revenue data for the last 6 months
    monthly_revenue = []
    for i in range(5, -1, -1):
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(days=30 * i)
        month_end = month_start + timedelta(days=32)
        month_start = month_start.replace(day=1)
        
        # Get orders in this month
        month_orders = Order.query.filter(
            Order.farmer_id == farmer.id,
            Order.created_at >= month_start,
            Order.created_at < month_end,
            Order.status == "delivered"
        ).all()
        
        revenue = sum(float(o.total_amount) for o in month_orders)
        order_count = len(month_orders)
        
        monthly_revenue.append({
            "month": month_start.strftime("%b"),
            "revenue": revenue,
            "orders": order_count
        })

    # Recent activity (last 10 orders)
    recent_orders = (
        Order.query
        .filter_by(farmer_id=farmer.id)
        .order_by(Order.created_at.desc())
        .limit(10)
        .all()
    )

    recent_activity = []
    for order in recent_orders:
        buyer = Buyer.query.get(order.buyer_id)
        buyer_user = User.query.filter_by(id=str(buyer.user_id)).first() if buyer else None
        buyer_name = buyer_user.full_name if buyer_user else "Unknown Buyer"
        
        recent_activity.append({
            "type": "order",
            "title": f"New order received",
            "description": f"{buyer_name} - KES {float(order.total_amount):,.0f}",
            "time_ago": get_time_ago(order.created_at),
            "status": order.status
        })

    # Add reviews to activity
    for review in user_reviews[-5:]:
        reviewer = User.query.get(review.reviewer_id)
        recent_activity.append({
            "type": "review",
            "title": f"New review received",
            "description": f"{reviewer.full_name if reviewer else 'User'} - {review.rating} stars",
            "time_ago": get_time_ago(review.created_at),
            "rating": review.rating
        })

    # Sort by time
    recent_activity.sort(key=lambda x: x["time_ago"], reverse=True)
    recent_activity = recent_activity[:10]

    return jsonify({
        "stats": {
            "total_revenue": round(total_revenue, 2),
            "total_orders": total_orders,
            "avg_order_value": round(avg_order_value, 2),
            "avg_rating": round(avg_rating, 1),
            "review_count": review_count,
            "active_listings": active_listings,
            "pending_orders": pending_orders,
        },
        "monthly_revenue": monthly_revenue,
        "recent_activity": recent_activity,
        "revenue_change": calculate_revenue_change(completed_orders),
        "orders_change": calculate_orders_change(completed_orders),
    }), 200


def get_time_ago(dt):
    """Helper function to get time ago string"""
    if not dt:
        return "Unknown"
    
    now = datetime.utcnow()
    diff = now - dt
    
    if diff.days > 30:
        return f"{diff.days // 30} months ago"
    elif diff.days > 0:
        return f"{diff.days} days ago"
    elif diff.seconds > 3600:
        return f"{diff.seconds // 3600} hours ago"
    elif diff.seconds > 60:
        return f"{diff.seconds // 60} minutes ago"
    else:
        return "Just now"


def calculate_revenue_change(orders):
    """Calculate revenue change compared to previous period"""
    if not orders:
        return 0
    
    now = datetime.utcnow()
    last_month_start = (now.replace(day=1) - timedelta(days=30)).replace(day=1)
    this_month_start = now.replace(day=1)
    
    this_month_revenue = sum(
        float(o.total_amount) 
        for o in orders 
        if o.created_at >= this_month_start
    )
    
    last_month_revenue = sum(
        float(o.total_amount) 
        for o in orders 
        if last_month_start <= o.created_at < this_month_start
    )
    
    if last_month_revenue == 0:
        return 100 if this_month_revenue > 0 else 0
    
    return round(((this_month_revenue - last_month_revenue) / last_month_revenue) * 100, 1)


def calculate_orders_change(orders):
    """Calculate order count change compared to previous period"""
    if not orders:
        return 0
    
    now = datetime.utcnow()
    last_month_start = (now.replace(day=1) - timedelta(days=30)).replace(day=1)
    this_month_start = now.replace(day=1)
    
    this_month_count = sum(
        1 for o in orders if o.created_at >= this_month_start
    )
    
    last_month_count = sum(
        1 for o in orders 
        if last_month_start <= o.created_at < this_month_start
    )
    
    if last_month_count == 0:
        return 100 if this_month_count > 0 else 0
    
    return round(((this_month_count - last_month_count) / last_month_count) * 100, 1)

