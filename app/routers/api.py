import time
from datetime import datetime
from typing import Annotated, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select, func

from app.internal.auth.authentication import (
    DetailedUser,
    create_user,
    get_api_authenticated_user,
    raise_for_invalid_password,
)
from app.internal.models import GroupEnum, User
from app.util.db import get_session

router = APIRouter(
    prefix="/api", 
    tags=["API"],
    responses={
        401: {"description": "Unauthorized - Invalid or missing API key"},
        403: {"description": "Forbidden - Insufficient permissions"},
    },
)

# Store startup time for uptime calculation
startup_time = time.time()


class UserResponse(BaseModel):
    """User information response model"""
    username: str = Field(..., description="Unique username")
    group: GroupEnum = Field(..., description="User group determining permissions")
    root: bool = Field(..., description="Whether this is the root admin user")
    
    @classmethod
    def from_user(cls, user: User) -> "UserResponse":
        return cls(
            username=user.username,
            group=user.group,
            root=user.root,
        )


class UserCreate(BaseModel):
    """User creation request model"""
    username: str = Field(..., min_length=1, max_length=100, description="Unique username")
    password: str = Field(..., min_length=1, description="User password")
    group: GroupEnum = Field(GroupEnum.untrusted, description="User group (untrusted, trusted, admin)")
    root: bool = Field(False, description="Whether to create as root admin user")


class UserUpdate(BaseModel):
    """User update request model"""
    password: Optional[str] = Field(None, min_length=1, description="New password (optional)")
    group: Optional[GroupEnum] = Field(None, description="New user group (optional)")


class UsersListResponse(BaseModel):
    """Users list response model"""
    users: List[UserResponse] = Field(..., description="List of users")
    total: int = Field(..., description="Total number of users")


class HealthResponse(BaseModel):
    """Health check response model"""
    status: str = Field(..., description="Health status")
    timestamp: datetime = Field(..., description="Current timestamp")
    uptime: float = Field(..., description="Uptime in seconds")



class VersionResponse(BaseModel):
    """Version information response model"""
    name: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    description: str = Field(..., description="Application description")
    repository: str = Field(..., description="Source code repository")
    python_version: str = Field(..., description="Python version")
    fastapi_version: str = Field(..., description="FastAPI version")





@router.get("/health", response_model=HealthResponse, tags=["System"])
def health_check():
    return Response(status_code=200)


@router.get("/users", response_model=UsersListResponse, tags=["Users"])
def list_users(
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[
        DetailedUser, Depends(get_api_authenticated_user(GroupEnum.admin))
    ],
    limit: int = Query(50, ge=1, le=100, description="Maximum number of users to return"),
    offset: int = Query(0, ge=0, description="Number of users to skip"),
):
    """
    List all users in the system.
    
    **Requires:** Admin privileges
    
    **Authentication:** Bearer token (API key)
    
    Returns a paginated list of all users with their basic information.
    """
    query = select(User).offset(offset).limit(limit)
    users = session.exec(query).all()
    total = session.exec(select(func.count()).select_from(User)).one()
    
    return UsersListResponse(
        users=[UserResponse.from_user(user) for user in users],
        total=total,
    )


@router.get("/users/me", response_model=UserResponse, tags=["Users"])
def get_current_user(
    current_user: Annotated[DetailedUser, Depends(get_api_authenticated_user())],
):
    """
    Get current user's information.
    
    **Requires:** Any authenticated user
    
    **Authentication:** Bearer token (API key)
    
    Returns information about the user associated with the provided API key.
    """
    return UserResponse.from_user(current_user)


@router.get("/users/{username}", response_model=UserResponse, tags=["Users"])
def get_user(
    username: str,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[
        DetailedUser, Depends(get_api_authenticated_user(GroupEnum.admin))
    ],
):
    """
    Get information about a specific user.
    
    **Requires:** Admin privileges
    
    **Authentication:** Bearer token (API key)
    
    Returns detailed information about the specified user.
    """
    user = session.get(User, username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    return UserResponse.from_user(user)


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED, tags=["Users"])
def create_new_user(
    user_data: UserCreate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[
        DetailedUser, Depends(get_api_authenticated_user(GroupEnum.admin))
    ],
):
    """
    Create a new user in the system.
    
    **Requires:** Admin privileges
    
    **Authentication:** Bearer token (API key)
    
    Creates a new user with the specified username, password, and group.
    Username must be unique within the system.
    """
    existing_user = session.get(User, user_data.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )
    
    try:
        raise_for_invalid_password(session, user_data.password, ignore_confirm=True)
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=e.detail,
        )
    
    user = create_user(
        username=user_data.username,
        password=user_data.password,
        group=user_data.group,
        root=user_data.root,
    )
    
    session.add(user)
    session.commit()
    
    return UserResponse.from_user(user)


@router.put("/users/{username}", response_model=UserResponse, tags=["Users"])
def update_user(
    username: str,
    user_data: UserUpdate,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[
        DetailedUser, Depends(get_api_authenticated_user(GroupEnum.admin))
    ],
):
    """
    Update an existing user.
    
    **Requires:** Admin privileges
    
    **Authentication:** Bearer token (API key)
    
    Updates the specified user's password and/or group.
    Root users cannot have their group changed.
    """
    user = session.get(User, username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    if user.root and user_data.group is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change root user's group",
        )
    
    if user_data.password is not None:
        try:
            raise_for_invalid_password(session, user_data.password, ignore_confirm=True)
        except HTTPException as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=e.detail,
            )
        
        updated_user = create_user(username, user_data.password, user.group)
        user.password = updated_user.password
    
    if user_data.group is not None:
        user.group = user_data.group
    
    session.add(user)
    session.commit()
    
    return UserResponse.from_user(user)


@router.delete("/users/{username}", status_code=status.HTTP_204_NO_CONTENT, tags=["Users"])
def delete_user(
    username: str,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[
        DetailedUser, Depends(get_api_authenticated_user(GroupEnum.admin))
    ],
):
    """
    Delete a user from the system.
    
    **Requires:** Admin privileges
    
    **Authentication:** Bearer token (API key)
    
    Permanently removes the specified user from the system.
    Cannot delete own user or root users.
    """
    if username == current_user.username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete own user",
        )
    
    user = session.get(User, username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    if user.root:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete root user",
        )
    
    session.delete(user)
    session.commit()