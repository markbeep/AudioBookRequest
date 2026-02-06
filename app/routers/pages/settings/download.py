from typing import Annotated

from fastapi import APIRouter, Depends, Form, Response, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.models import GroupEnum
from app.internal.ranking.quality import IndexerFlag, QualityRange, quality_config
from app.routers.api.settings.download import (
    UpdateDownloadSettings,
)
from app.routers.api.settings.download import (
    update_download_settings as api_update_download_settings,
)
from app.util.db import get_session
from app.util.templates import catalog_response, catalog_response_toast

router = APIRouter(prefix="/download")


@router.get("")
def read_download(
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    auto_download = quality_config.get_auto_download(session)
    flac_range = quality_config.get_range(session, "quality_flac")
    m4b_range = quality_config.get_range(session, "quality_m4b")
    mp3_range = quality_config.get_range(session, "quality_mp3")
    unknown_audio_range = quality_config.get_range(session, "quality_unknown_audio")
    unknown_range = quality_config.get_range(session, "quality_unknown")
    min_seeders = quality_config.get_min_seeders(session)
    name_ratio = quality_config.get_name_exists_ratio(session)
    title_ratio = quality_config.get_title_exists_ratio(session)
    flags = quality_config.get_indexer_flags(session)

    return catalog_response(
        "Settings.Download.Index",
        user=admin_user,
        auto_download=auto_download,
        flac_range=flac_range,
        m4b_range=m4b_range,
        mp3_range=mp3_range,
        unknown_audio_range=unknown_audio_range,
        unknown_range=unknown_range,
        min_seeders=min_seeders,
        name_ratio=name_ratio,
        title_ratio=title_ratio,
        indexer_flags=flags,
    )


@router.post("/hx-sliders")
def update_download(
    flac_from: Annotated[float, Form()],
    flac_to: Annotated[float, Form()],
    m4b_from: Annotated[float, Form()],
    m4b_to: Annotated[float, Form()],
    mp3_from: Annotated[float, Form()],
    mp3_to: Annotated[float, Form()],
    unknown_audio_from: Annotated[float, Form()],
    unknown_audio_to: Annotated[float, Form()],
    unknown_from: Annotated[float, Form()],
    unknown_to: Annotated[float, Form()],
    min_seeders: Annotated[int, Form()],
    name_ratio: Annotated[int, Form()],
    title_ratio: Annotated[int, Form()],
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
    auto_download: Annotated[bool, Form()] = False,
):
    flac = QualityRange(from_kbits=flac_from, to_kbits=flac_to)
    m4b = QualityRange(from_kbits=m4b_from, to_kbits=m4b_to)
    mp3 = QualityRange(from_kbits=mp3_from, to_kbits=mp3_to)
    unknown_audio = QualityRange(
        from_kbits=unknown_audio_from, to_kbits=unknown_audio_to
    )
    unknown = QualityRange(from_kbits=unknown_from, to_kbits=unknown_to)

    api_update_download_settings(
        UpdateDownloadSettings(
            auto_download=auto_download,
            flac_range=flac,
            m4b_range=m4b,
            mp3_range=mp3,
            unknown_audio_range=unknown_audio,
            unknown_range=unknown,
            min_seeders=min_seeders,
            name_ratio=name_ratio,
            title_ratio=title_ratio,
        ),
        session,
        admin_user,
    )

    return catalog_response_toast(
        "Settings.Download.Sliders",
        "Settings updated",
        "success",
        auto_download=auto_download,
        flac_range=flac,
        m4b_range=m4b,
        mp3_range=mp3,
        unknown_audio_range=unknown_audio,
        unknown_range=unknown,
        min_seeders=min_seeders,
        name_ratio=name_ratio,
        title_ratio=title_ratio,
    )


@router.delete("")
def reset_download_setings(
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    _ = admin_user
    quality_config.reset_all(session)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.post("/hx-flags")
def add_indexer_flag(
    session: Annotated[Session, Depends(get_session)],
    flag: Annotated[str, Form()],
    score: Annotated[int, Form()],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    _ = admin_user
    flags = quality_config.get_indexer_flags(session)
    if not any(f.flag == flag for f in flags):
        flags.append(IndexerFlag(flag=flag.lower(), score=score))
        quality_config.set_indexer_flags(session, flags)

    return catalog_response(
        "Settings.Download.IndexerFlags",
        indexer_flags=flags,
    )


@router.delete("/hx-flags/{flag}")
def remove_indexer_flag(
    flag: str,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    _ = admin_user
    flags = quality_config.get_indexer_flags(session)
    flags = [f for f in flags if f.flag != flag]
    quality_config.set_indexer_flags(session, flags)
    return catalog_response(
        "Settings.Download.IndexerFlags",
        indexer_flags=flags,
    )
