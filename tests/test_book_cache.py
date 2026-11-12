from datetime import UTC, datetime

from sqlmodel import Session, select

from app.internal.audible.search import upsert_books
from app.internal.models import Audiobook, AudiobookRequest
from tests.constants import FULFILLED_ASIN


def test_upsert_books_preserves_request_state(db: Session) -> None:
    existing = db.get(Audiobook, FULFILLED_ASIN)
    assert existing is not None
    existing.admin_note = "keep me"
    db.add(existing)
    db.commit()

    fresh = Audiobook(
        asin=FULFILLED_ASIN,
        title="Refreshed Title",
        subtitle=None,
        authors=["Mock Author"],
        narrators=["Mock Narrator"],
        cover_image=None,
        release_date=datetime(2021, 1, 1, tzinfo=UTC),
        runtime_length_min=123,
    )
    stored = upsert_books(db, [fresh])
    db.refresh(stored[0])

    assert stored[0].fulfilled is True
    assert stored[0].admin_note == "keep me"
    assert stored[0].title == "Refreshed Title"
    assert stored[0].runtime_length_min == 123
    assert db.exec(
        select(AudiobookRequest).where(AudiobookRequest.asin == FULFILLED_ASIN)
    ).all()

    new = Audiobook(
        asin="B00NEWBOOK",
        title="New Book",
        subtitle=None,
        authors=["Mock Author"],
        narrators=["Mock Narrator"],
        cover_image=None,
        release_date=datetime(2021, 1, 1, tzinfo=UTC),
        runtime_length_min=456,
    )
    upsert_books(db, [new])
    assert db.get(Audiobook, "B00NEWBOOK") is not None
