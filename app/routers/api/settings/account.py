import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, Security
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.internal.auth.authentication import (
    AnyAuth,
    DetailedUser,
    create_api_key,
    create_user,
    is_correct_password,
    raise_for_invalid_password,
)
from app.internal.models import APIKey, APIKeyResponse, User
from app.util.db import get_session

router = APIRouter(prefix="/account", tags=["Account"])


class CreateAPIKeyRequest(BaseModel):
    name: str = Field(min_length=1)


class CreateAPIKeyResponse(BaseModel):
    name: str
    key: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str
    confirm_password: str


@router.get("/api-keys", response_model=list[APIKeyResponse])
def list_api_keys(
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(AnyAuth())],
):
    api_keys = session.exec(
        select(APIKey).where(APIKey.user_username == user.username)
    ).all()
    return api_keys


@router.post("/api-keys", response_model=CreateAPIKeyResponse)
def create_new_api_key(
    body: CreateAPIKeyRequest,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(AnyAuth())],
):
    name = body.name.strip()
    same_name_key = session.exec(
        select(APIKey).where(
            APIKey.user_username == user.username,
            APIKey.name == name,
        )
    ).first()
    if same_name_key:
        raise HTTPException(status_code=400, detail="API key name must be unique")

    api_key, private_key = create_api_key(user, name)
    session.add(api_key)
    session.commit()

    return CreateAPIKeyResponse(name=name, key=private_key)


@router.delete("/api-keys/{id}")
def delete_api_key(
    id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(AnyAuth())],
):
    try:
        uuid_id = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID")

    api_key = session.exec(
        select(APIKey).where(
            APIKey.user_username == user.username,
            APIKey.id == uuid_id,
        )
    ).first()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    session.delete(api_key)
    session.commit()
    return Response(status_code=204)


@router.patch("/api-keys/{id}/toggle")
def toggle_api_key(
    id: str,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(AnyAuth())],
):
    try:
        uuid_id = uuid.UUID(id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID")

    api_key = session.exec(
        select(APIKey).where(
            APIKey.user_username == user.username,
            APIKey.id == uuid_id,
        )
    ).first()
    if not api_key:
        raise HTTPException(status_code=404, detail="API key not found")

    api_key.enabled = not api_key.enabled
    session.add(api_key)
    session.commit()
    return Response(status_code=204)


@router.put("/password")
def change_password(
    body: ChangePasswordRequest,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(AnyAuth())],
):
    if not is_correct_password(user, body.old_password):
        raise HTTPException(status_code=400, detail="Old password is incorrect")

    raise_for_invalid_password(session, body.new_password, body.confirm_password)

    new_user = create_user(user.username, body.new_password, user.group)
    old_user = session.exec(select(User).where(User.username == user.username)).one()
    old_user.password = new_user.password
    session.add(old_user)
    session.commit()

    return Response(status_code=204)
