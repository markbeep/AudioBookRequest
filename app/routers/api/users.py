from typing import Annotated, List

from fastapi import APIRouter, Depends, HTTPException, Query, Security, status
from pydantic import BaseModel, Field
from sqlmodel import Session, func, select

from app.internal.auth.authentication import (
    AnyAuth,
    DetailedUser,
    create_user,
    raise_for_invalid_password,
)
from app.internal.models import GroupEnum, User
from app.util.db import get_session

router = APIRouter(prefix="/users", tags=["Users"])


class UserResponse(BaseModel):
    username: str = Field(description="Unique username")
    group: GroupEnum = Field(description="User group determining permissions")
    root: bool = Field(description="Whether this is the root admin user")

    @classmethod
    def from_user(cls, user: User) -> "UserResponse":
        return cls(
            username=user.username,
            group=user.group,
            root=user.root,
        )


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=100, description="Unique username")
    password: str = Field(min_length=1, description="User password")
    group: GroupEnum = Field(
        GroupEnum.untrusted, description="User group (untrusted, trusted, admin)"
    )
    root: bool = Field(False, description="Whether to create as root admin user")
    extra_data: str | None = Field(None, description="Optional extra data for the user")


class UserUpdate(BaseModel):
    password: str | None = Field(
        None, min_length=1, description="New password (optional)"
    )
    group: GroupEnum | None = Field(None, description="New user group (optional)")
    extra_data: str | None = Field(None, description="Optional extra data for the user")


class UsersListResponse(BaseModel):
    users: List[UserResponse] = Field(description="List of users")
    total: int = Field(description="Total number of users")


@router.get("/", response_model=UsersListResponse)
def list_users(
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
    limit: Annotated[
        int, Query(ge=1, le=100, description="Maximum number of users to return")
    ] = 50,
    offset: Annotated[int, Query(ge=0, description="Number of users to skip")] = 0,
):
    """
    Returns a paginated list of all users with their basic information.

    **Requires:** Admin privileges
    """
    query = select(User).offset(offset).limit(limit)
    users = session.exec(query).all()
    total = session.exec(select(func.count()).select_from(User)).one()

    return UsersListResponse(
        users=[UserResponse.from_user(user) for user in users],
        total=total,
    )


@router.get("/me", response_model=UserResponse)
def get_current_user(
    current_user: Annotated[DetailedUser, Security(AnyAuth())],
):
    """
    Returns information about the user associated with the provided API key.

    **Requires:** Any authenticated user
    """
    return UserResponse.from_user(current_user)


@router.get("/{username}", response_model=UserResponse)
def get_user(
    username: str,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    """
    Returns detailed information about the specified user.

    **Requires:** Admin privileges
    """
    user = session.get(User, username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return UserResponse.from_user(user)


@router.post("/", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_new_user(
    user_data: UserCreate,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    """
    Creates a new user with the specified username, password, and group.
    Username must be unique within the system.

    **Requires:** Admin privileges
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
        extra_data=user_data.extra_data,
    )

    session.add(user)
    session.commit()

    return UserResponse.from_user(user)


@router.put("/{username}", response_model=UserResponse)
def update_user(
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
    session: Annotated[Session, Depends(get_session)],
    username: str,
    user_data: UserUpdate,
):
    """
    Updates the specified user's password and/or group.
    Root users cannot have their group changed.

    **Requires:** Admin privileges
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

        # create user to get pw hash
        updated_user = create_user(
            username,
            user_data.password,
            user.group,
            extra_data=user.extra_data,
        )
        user.password = updated_user.password

    if user_data.extra_data is not None:
        user.extra_data = (
            user_data.extra_data.strip() if user_data.extra_data.strip() != "" else None
        )

    if user_data.group is not None:
        user.group = user_data.group

    session.add(user)
    session.commit()

    return UserResponse.from_user(user)


@router.delete("/{username}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    username: str,
    session: Annotated[Session, Depends(get_session)],
    current_user: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    """
    Permanently removes the specified user from the system.
    Cannot delete own user or root users.

    **Requires:** Admin privileges
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
