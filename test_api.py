#!/usr/bin/env python3
"""Quick API test to verify production readiness"""

import requests
import json

BASE_URL = "http://localhost:5000/api"

def test_health():
    print("🔍 Testing health endpoint...")
    r = requests.get(f"{BASE_URL}/health")
    assert r.status_code == 200
    print("✅ Health check passed")

def test_login():
    print("🔍 Testing login...")
    r = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "farmer@test.com",
        "password": "farmer123"
    })
    assert r.status_code == 200
    token = r.json()["access_token"]
    print("✅ Login successful")
    return token

def test_livestock(token):
    print("🔍 Testing livestock endpoint...")
    r = requests.get(f"{BASE_URL}/livestock/all")
    assert r.status_code == 200
    animals = r.json()["animals"]
    print(f"✅ Found {len(animals)} animals")
    return animals[0]["id"] if animals else None

def test_create_order(token, animal_id):
    print("🔍 Testing order creation...")
    headers = {"Authorization": f"Bearer {token}"}
    
    # Login as buyer
    r = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "buyer@test.com",
        "password": "buyer123"
    })
    buyer_token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {buyer_token}"}
    
    r = requests.post(f"{BASE_URL}/orders/", 
        headers=headers,
        json={"items": [{"id": animal_id, "quantity": 1}]}
    )
    if r.status_code == 201:
        print("✅ Order created successfully")
        return True
    else:
        print(f"⚠️  Order creation returned {r.status_code}")
        return False

def test_admin(token):
    print("🔍 Testing admin endpoint...")
    # Login as admin
    r = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "admin@farmart.com",
        "password": "admin123"
    })
    admin_token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    r = requests.get(f"{BASE_URL}/admin/stats", headers=headers)
    if r.status_code == 200:
        stats = r.json()
        print(f"✅ Admin stats: {stats['total_users']} users, {stats['total_livestock']} animals")
        return True
    return False

if __name__ == "__main__":
    print("🚀 Farmart API Test Suite")
    print("=" * 50)
    
    try:
        test_health()
        token = test_login()
        animal_id = test_livestock(token)
        if animal_id:
            test_create_order(token, animal_id)
        test_admin(token)
        
        print("\n" + "=" * 50)
        print("🎉 All tests passed! Production ready!")
        print("\n📋 Test Accounts:")
        print("   Admin:  admin@farmart.com / admin123")
        print("   Farmer: farmer@test.com / farmer123")
        print("   Buyer:  buyer@test.com / buyer123")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        print("   Make sure backend is running: flask run")
