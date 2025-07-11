#!/usr/bin/env python3
"""
Script to generate OpenAPI specification for AudioBookRequest API
"""
import json
from app.main import app

def generate_openapi_spec():
    """Generate and save OpenAPI specification to file"""
    openapi_spec = app.openapi()
    
    # Add additional metadata
    openapi_spec["info"]["contact"] = {
        "name": "AudioBookRequest",
        "url": "https://github.com/markbeep/AudioBookRequest"
    }
    
    openapi_spec["info"]["license"] = {
        "name": "MIT",
        "url": "https://github.com/markbeep/AudioBookRequest/blob/main/LICENSE"
    }
    
    # Add servers
    openapi_spec["servers"] = [
        {
            "url": "http://localhost:8000",
            "description": "Development server"
        }
    ]
    
    # Add security schemes
    openapi_spec["components"]["securitySchemes"] = {
        "ApiKeyAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "API Key",
            "description": "API Key authentication using Bearer token"
        }
    }
    
    # Add global security requirement
    openapi_spec["security"] = [
        {"ApiKeyAuth": []}
    ]
    
    # Write to file
    with open("api_spec.json", "w") as f:
        json.dump(openapi_spec, f, indent=2)
    
    print("OpenAPI specification generated successfully!")
    print("Files created:")
    print("- api_spec.json: Full OpenAPI specification")
    print("\nTo view the interactive docs:")
    print("1. Set ABR_APP__OPENAPI_ENABLED=true")
    print("2. Start the server: uv run fastapi dev")
    print("3. Visit: http://localhost:8000/docs")

if __name__ == "__main__":
    generate_openapi_spec()