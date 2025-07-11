# AudioBookRequest API Documentation

## Overview

AudioBookRequest provides a RESTful API for managing users and audiobook requests. The API uses Bearer token authentication with API keys that can be generated through the web interface.

## Base URL

```
http://localhost:8000/api/v1
```

## Authentication

All API endpoints require authentication using an API key. Include the API key in the Authorization header:

```
Authorization: Bearer <your-api-key>
```

### Getting an API Key

1. Log into the AudioBookRequest web interface
2. Go to Settings → Account
3. Create a new API key with a descriptive name
4. Copy the generated key (it will only be shown once)

## User Groups

AudioBookRequest has three user groups with different permissions:

- **untrusted**: Can make requests that require manual approval
- **trusted**: Can make requests that are automatically processed
- **admin**: Can manage users, settings, and all system functions

## Endpoints

### System Endpoints

#### Health Check

```http
GET /api/v1/health
```

**Requires:** No authentication

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T12:00:00Z",
  "uptime": 3600.5
}
```

**Description:** Basic health check endpoint for monitoring systems, load balancers, and container orchestration.

#### System Status

```http
GET /api/v1/status
```

**Requires:** Admin privileges

**Response:**
```json
{
  "status": "healthy",
  "version": "1.3.0",
  "database": "healthy",
  "users_count": 5,
  "requests_count": 128,
  "api_keys_count": 3,
  "timestamp": "2024-01-01T12:00:00Z"
}
```

**Description:** Comprehensive system status including database health and usage statistics.

#### Version Information

```http
GET /api/v1/version
```

**Requires:** No authentication

**Response:**
```json
{
  "name": "AudioBookRequest",
  "version": "1.3.0",
  "description": "Your tool for handling audiobook requests on a Plex/Audiobookshelf/Jellyfin instance",
  "repository": "https://github.com/markbeep/AudioBookRequest",
  "python_version": "3.12.7",
  "fastapi_version": "0.115.6"
}
```

**Description:** Application version and build information for debugging and compatibility checking.

#### System Metrics

```http
GET /api/v1/metrics
```

**Requires:** Admin privileges

**Response:**
```json
{
  "users": {
    "untrusted": 2,
    "trusted": 2,
    "admin": 1
  },
  "requests": {
    "total": 128,
    "downloaded": 95,
    "pending": 33
  },
  "api_keys": {
    "total": 5,
    "enabled": 3,
    "disabled": 2
  },
  "timestamp": "2024-01-01T12:00:00Z"
}
```

**Description:** Detailed system metrics for monitoring, analytics, and capacity planning.

### User Management Endpoints

#### List Users

```http
GET /api/v1/users
```

**Requires:** Admin privileges

**Parameters:**
- `limit` (query, optional): Maximum number of users to return (1-100, default: 50)
- `offset` (query, optional): Number of users to skip (default: 0)

**Response:**
```json
{
  "users": [
    {
      "username": "john_doe",
      "group": "trusted",
      "root": false
    }
  ],
  "total": 1
}
```

### Get User

```http
GET /api/v1/users/{username}
```

**Requires:** Admin privileges

**Parameters:**
- `username` (path): Username to retrieve

**Response:**
```json
{
  "username": "john_doe",
  "group": "trusted",
  "root": false
}
```

### Create User

```http
POST /api/v1/users
```

**Requires:** Admin privileges

**Request Body:**
```json
{
  "username": "new_user",
  "password": "secure_password",
  "group": "untrusted",
  "root": false
}
```

**Response:** `201 Created`
```json
{
  "username": "new_user",
  "group": "untrusted",
  "root": false
}
```

### Update User

```http
PUT /api/v1/users/{username}
```

**Requires:** Admin privileges

**Parameters:**
- `username` (path): Username to update

**Request Body:**
```json
{
  "password": "new_password",
  "group": "trusted"
}
```

**Response:**
```json
{
  "username": "updated_user",
  "group": "trusted",
  "root": false
}
```

### Delete User

```http
DELETE /api/v1/users/{username}
```

**Requires:** Admin privileges

**Parameters:**
- `username` (path): Username to delete

**Response:** `204 No Content`

**Note:** Cannot delete own user or root users.

### Get Current User

```http
GET /api/v1/users/me
```

**Requires:** Any authenticated user

**Response:**
```json
{
  "username": "current_user",
  "group": "trusted",
  "root": false
}
```

## Error Responses

The API uses standard HTTP status codes:

- `200 OK`: Success
- `201 Created`: Resource created successfully
- `204 No Content`: Success with no response body
- `400 Bad Request`: Invalid request data
- `401 Unauthorized`: Missing or invalid API key
- `403 Forbidden`: Insufficient permissions
- `404 Not Found`: Resource not found
- `409 Conflict`: Resource already exists

### Error Response Format

```json
{
  "detail": "Error message describing what went wrong"
}
```

## Examples

### Using cURL

```bash
# Set your API key
export API_KEY="your-api-key-here"

# System endpoints (no auth required)
curl http://localhost:8000/api/v1/health
curl http://localhost:8000/api/v1/version

# System endpoints (admin required)
curl -H "Authorization: Bearer $API_KEY" \
  http://localhost:8000/api/v1/status

curl -H "Authorization: Bearer $API_KEY" \
  http://localhost:8000/api/v1/metrics

# User management
curl -H "Authorization: Bearer $API_KEY" \
  http://localhost:8000/api/v1/users

curl -H "Authorization: Bearer $API_KEY" \
  http://localhost:8000/api/v1/users/me

# Create a new user
curl -X POST \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"username": "newuser", "password": "password123", "group": "trusted"}' \
  http://localhost:8000/api/v1/users

# Update user
curl -X PUT \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"group": "admin"}' \
  http://localhost:8000/api/v1/users/newuser

# Delete user
curl -X DELETE \
  -H "Authorization: Bearer $API_KEY" \
  http://localhost:8000/api/v1/users/newuser
```

### Using Python requests

```python
import requests

# Your API key
API_KEY = "your-api-key-here"
BASE_URL = "http://localhost:8000/api/v1"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# System endpoints (no auth required)
health = requests.get(f"{BASE_URL}/health").json()
version = requests.get(f"{BASE_URL}/version").json()

# System endpoints (admin required)
status = requests.get(f"{BASE_URL}/status", headers=headers).json()
metrics = requests.get(f"{BASE_URL}/metrics", headers=headers).json()

# User management
users = requests.get(f"{BASE_URL}/users", headers=headers).json()
current_user = requests.get(f"{BASE_URL}/users/me", headers=headers).json()

# Create user
user_data = {
    "username": "newuser",
    "password": "password123",
    "group": "trusted"
}
new_user = requests.post(f"{BASE_URL}/users", json=user_data, headers=headers).json()

# Update user
update_data = {"group": "admin"}
updated_user = requests.put(f"{BASE_URL}/users/newuser", json=update_data, headers=headers).json()

# Delete user
requests.delete(f"{BASE_URL}/users/newuser", headers=headers)
```

## Interactive Documentation

For a complete interactive API documentation with the ability to test endpoints directly:

1. Set the environment variable: `ABR_APP__OPENAPI_ENABLED=true`
2. Start the server: `uv run fastapi dev`
3. Visit: `http://localhost:8000/docs` (Swagger UI) or `http://localhost:8000/redoc` (ReDoc)

## Rate Limiting

Currently, there are no rate limits implemented. However, it's recommended to implement reasonable rate limiting in production environments.

## Security Considerations

- Store API keys securely and never commit them to version control
- Use HTTPS in production environments
- Regularly rotate API keys
- Monitor API usage for unusual patterns
- Implement proper logging for security auditing