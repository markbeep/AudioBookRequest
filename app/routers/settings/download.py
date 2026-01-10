from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, Response, Security
from sqlmodel import Session

from app.internal.auth.authentication import ABRAuth, DetailedUser
from app.internal.models import GroupEnum
from app.internal.ranking.quality import IndexerFlag, QualityRange, quality_config
from app.util.db import get_session
from app.util.templates import template_response

router = APIRouter(prefix="/download")


@router.get("")
def read_download(
    request: Request,
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

    return template_response(
        "settings_page/download.html",
        request,
        admin_user,
        {
            "page": "download",
            "auto_download": auto_download,
            "flac_range": flac_range,
            "m4b_range": m4b_range,
            "mp3_range": mp3_range,
            "unknown_audio_range": unknown_audio_range,
            "unknown_range": unknown_range,
            "min_seeders": min_seeders,
            "name_ratio": name_ratio,
            "title_ratio": title_ratio,
            "indexer_flags": flags,
        },
    )


@router.post("")
def update_download(
    request: Request,
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

    quality_config.set_auto_download(session, auto_download)
    quality_config.set_range(session, "quality_flac", flac)
    quality_config.set_range(session, "quality_m4b", m4b)
    quality_config.set_range(session, "quality_mp3", mp3)
    quality_config.set_range(session, "quality_unknown_audio", unknown_audio)
    quality_config.set_range(session, "quality_unknown", unknown)
    quality_config.set_min_seeders(session, min_seeders)
    quality_config.set_name_exists_ratio(session, name_ratio)
    quality_config.set_title_exists_ratio(session, title_ratio)

    return template_response(
        "settings_page/download.html",
        request,
        admin_user,
        {
            "page": "download",
            "success": "Settings updated",
            "auto_download": auto_download,
            "flac_range": flac,
            "m4b_range": m4b,
            "mp3_range": mp3,
            "unknown_audio_range": unknown_audio,
            "unknown_range": unknown,
            "min_seeders": min_seeders,
            "name_ratio": name_ratio,
            "title_ratio": title_ratio,
        },
        block_name="form",
    )


@router.delete("")
def reset_download_setings(
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    _ = admin_user
    quality_config.reset_all(session)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


@router.post("/indexer-flag")
def add_indexer_flag(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    flag: Annotated[str, Form()],
    score: Annotated[int, Form()],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    flags = quality_config.get_indexer_flags(session)
    if not any(f.flag == flag for f in flags):
        flags.append(IndexerFlag(flag=flag.lower(), score=score))
        quality_config.set_indexer_flags(session, flags)

    return template_response(
        "settings_page/download.html",
        request,
        admin_user,
        {"page": "download", "indexer_flags": flags},
        block_name="flags",
    )


@router.delete("/indexer-flag/{flag}")
def remove_indexer_flag(
    request: Request,
    flag: str,
    session: Annotated[Session, Depends(get_session)],
    admin_user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    flags = quality_config.get_indexer_flags(session)
    flags = [f for f in flags if f.flag != flag]
    quality_config.set_indexer_flags(session, flags)
    return template_response(
        "settings_page/download.html",
        request,
        admin_user,
        {"page": "download", "indexer_flags": flags},
        block_name="flags",
    )
