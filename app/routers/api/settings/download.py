from typing import Annotated

from fastapi import APIRouter, Depends, Response, Security
from pydantic import BaseModel
from sqlmodel import Session

from app.internal.auth.authentication import AnyAuth, DetailedUser
from app.internal.models import GroupEnum
from app.internal.ranking.quality import IndexerFlag, QualityRange, quality_config
from app.util.db import get_session

router = APIRouter(prefix="/download")


class DownloadSettings(BaseModel):
    auto_download: bool
    flac_range: QualityRange
    m4b_range: QualityRange
    mp3_range: QualityRange
    unknown_audio_range: QualityRange
    unknown_range: QualityRange
    min_seeders: int
    name_ratio: int
    title_ratio: int
    indexer_flags: list[IndexerFlag]


@router.get("", response_model=DownloadSettings)
def get_download_settings(
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    return DownloadSettings(
        auto_download=quality_config.get_auto_download(session),
        flac_range=quality_config.get_range(session, "quality_flac"),
        m4b_range=quality_config.get_range(session, "quality_m4b"),
        mp3_range=quality_config.get_range(session, "quality_mp3"),
        unknown_audio_range=quality_config.get_range(session, "quality_unknown_audio"),
        unknown_range=quality_config.get_range(session, "quality_unknown"),
        min_seeders=quality_config.get_min_seeders(session),
        name_ratio=quality_config.get_name_exists_ratio(session),
        title_ratio=quality_config.get_title_exists_ratio(session),
        indexer_flags=quality_config.get_indexer_flags(session),
    )


class UpdateDownloadSettings(BaseModel):
    auto_download: bool
    flac_range: QualityRange
    m4b_range: QualityRange
    mp3_range: QualityRange
    unknown_audio_range: QualityRange
    unknown_range: QualityRange
    min_seeders: int
    name_ratio: int
    title_ratio: int


@router.patch("", status_code=204)
def update_download_settings(
    body: UpdateDownloadSettings,
    session: Annotated[Session, Depends(get_session)],
    _: Annotated[DetailedUser, Security(AnyAuth(GroupEnum.admin))],
):
    quality_config.set_auto_download(session, body.auto_download)
    quality_config.set_range(session, "quality_flac", body.flac_range)
    quality_config.set_range(session, "quality_m4b", body.m4b_range)
    quality_config.set_range(session, "quality_mp3", body.mp3_range)
    quality_config.set_range(session, "quality_unknown_audio", body.unknown_audio_range)
    quality_config.set_range(session, "quality_unknown", body.unknown_range)
    quality_config.set_min_seeders(session, body.min_seeders)
    quality_config.set_name_exists_ratio(session, body.name_ratio)
    quality_config.set_title_exists_ratio(session, body.title_ratio)

    return Response(status_code=204)
