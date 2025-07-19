---
title: API
description: How to use the AudioBookRequest API
---
## Overview

AudioBookRequest provides a RESTful API for managing users and audiobook requests. The API uses Bearer token authentication with API keys that can be generated through the web interface.

## How to Create an API Key

Follow these steps to create an API key for accessing the AudioBookRequest API:

### Step 1: Access the Web Interface

1. Open your web browser and navigate to your AudioBookRequest instance
2. Log in with your username and password

### Step 2: Navigate to Account Settings

1. Once logged in, click on the **Settings** menu
2. Select **Account** from the settings options

### Step 3: Create a New API Key

1. In the Account settings page, look for the **API Keys** section
2. Click on **Create New API Key** or similar button
3. Enter a descriptive name for your API key (e.g., "Mobile App", "Automation Script", "Home Assistant Integration")
4. Click **Generate** or **Create**

### Step 4: Copy and Store Your API Key

1. **Important**: The API key will only be displayed once for security reasons
2. Copy the generated API key immediately and store it in a secure location
3. If you lose the key, you'll need to generate a new one

### Step 5: Use Your API Key

Include your API key in the Authorization header of your API requests:

```
Authorization: Bearer <your-api-key>
```

**Example using cURL:**
```bash
curl -H "Authorization: Bearer your-api-key-here" \
  http://localhost:8000/api/v1/users/me
```

## User Groups

AudioBookRequest has three user groups with different API permissions:

- **untrusted**: Can make requests that require manual approval
- **trusted**: Can make requests that are automatically processed  
- **admin**: Can manage users, settings, and access all system functions

## API Documentation

For complete API documentation with interactive testing capabilities:

1. Set the environment variable: `ABR_APP__OPENAPI_ENABLED=true`
2. Start the server: `uv run fastapi dev`
3. Visit: `http://localhost:8000/docs` (Swagger UI) or `http://localhost:8000/redoc` (ReDoc)

The interactive documentation provides:
- Complete endpoint documentation
- Request/response schemas
- Example requests and responses
- Ability to test endpoints directly in your browser
- Authentication setup and testing

## Security Considerations

- Store API keys securely and never commit them to version control
- Use HTTPS in production environments
- Regularly rotate API keys
- Monitor API usage for unusual patterns
- Implement proper logging for security auditing