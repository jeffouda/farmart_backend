#!/bin/bash
# Permanent Flask restart script

echo "🔄 Stopping Flask..."
pkill -9 flask
pkill -9 python
sleep 2

echo "🧹 Clearing Python cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null

echo "🚀 Starting Flask..."
cd /home/jeff/Farmart/Farmart_backend
flask run > flask.log 2>&1 &

sleep 3
echo "✅ Flask restarted!"
echo ""
echo "Testing endpoint..."
curl -s -X POST http://localhost:5000/api/negotiation/test123 \
  -H "Content-Type: application/json" \
  -d '{"content":"test","receiver_id":"test"}' | head -20
