from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Form, Request, Response, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.models import GroupEnum
from app.internal.media_management.config import media_management_config
from app.util.db import get_session
from app.util.templates import template_response

router = APIRouter(prefix="/media-management")

@router.get("")
async def read_media_management(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    return template_response(
        "settings_page/media_management.html",
        request,
        admin_user,
        {
            "page": "media-management",
            "library_path": media_management_config.get_library_path(session),
            "folder_pattern": media_management_config.get_folder_pattern(session),
            "use_series_folders": media_management_config.get_use_series_folders(session),
            "use_hardlinks": media_management_config.get_use_hardlinks(session),
        },
    )

@router.put("")
async def update_media_management(
    request: Request,
    library_path: Annotated[str, Form()],
    folder_pattern: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    use_series_folders: Annotated[bool, Form()] = False,
    use_hardlinks: Annotated[bool, Form()] = False,
):
    media_management_config.set_library_path(session, library_path)
    media_management_config.set_folder_pattern(session, folder_pattern)
    media_management_config.set_use_series_folders(session, use_series_folders)
    media_management_config.set_use_hardlinks(session, use_hardlinks)
    
    return template_response(
        "settings_page/media_management.html",
        request,
        admin_user,
        {
            "page": "media-management",
            "success": "Media management settings updated",
            "library_path": library_path,
            "folder_pattern": folder_pattern,
            "use_series_folders": use_series_folders,
            "use_hardlinks": use_hardlinks,
        },
        block_name="media_form"
    )