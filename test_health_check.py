#!/usr/bin/env python3
"""
Test script for Docker health check functionality
"""
import json
import sys
import time
from datetime import datetime

import requests


def test_health_endpoint():
    """Test the health check endpoint"""
    print("🔍 Testing health check endpoint...")
    
    try:
        response = requests.get("http://localhost:8000/api/v1/health", timeout=5)
        
        if response.status_code == 200:
            health_data = response.json()
            print(f"✅ Health check successful!")
            print(f"   Status: {health_data['status']}")
            print(f"   Uptime: {health_data['uptime']:.2f} seconds")
            print(f"   Timestamp: {health_data['timestamp']}")
            return True
        else:
            print(f"❌ Health check failed with status code: {response.status_code}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Health check failed with error: {e}")
        return False


def test_docker_health_check():
    """Test Docker health check command"""
    print("\n🐳 Testing Docker health check command...")
    
    import subprocess
    
    try:
        # This simulates what Docker would run
        result = subprocess.run(
            ["curl", "-f", "http://localhost:8000/api/v1/health"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            print("✅ Docker health check command successful!")
            return True
        else:
            print(f"❌ Docker health check command failed with return code: {result.returncode}")
            print(f"   Error: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Docker health check command timed out")
        return False
    except FileNotFoundError:
        print("⚠️  curl not found - this is expected in development, but curl is available in Docker")
        return None


def simulate_health_check_monitoring():
    """Simulate continuous health check monitoring"""
    print("\n📊 Simulating continuous health monitoring (5 checks)...")
    
    for i in range(5):
        print(f"\n--- Check {i+1}/5 ---")
        success = test_health_endpoint()
        
        if not success:
            print(f"❌ Health check failed on attempt {i+1}")
            return False
            
        if i < 4:  # Don't sleep after the last check
            time.sleep(2)
    
    print("✅ All health checks passed!")
    return True


def main():
    """Main test function"""
    print("🚀 AudioBookRequest Docker Health Check Test")
    print("=" * 50)
    
    # Test individual endpoint
    endpoint_success = test_health_endpoint()
    
    # Test Docker command
    docker_success = test_docker_health_check()
    
    # Test continuous monitoring
    monitoring_success = simulate_health_check_monitoring()
    
    print("\n📋 Test Results:")
    print(f"   Health Endpoint: {'✅ PASS' if endpoint_success else '❌ FAIL'}")
    print(f"   Docker Command: {'✅ PASS' if docker_success else '❌ FAIL' if docker_success is not None else '⚠️  SKIP'}")
    print(f"   Monitoring: {'✅ PASS' if monitoring_success else '❌ FAIL'}")
    
    if endpoint_success and monitoring_success:
        print("\n🎉 All tests passed! Health check is working correctly.")
        return 0
    else:
        print("\n💥 Some tests failed. Please check the server is running.")
        return 1


if __name__ == "__main__":
    sys.exit(main())