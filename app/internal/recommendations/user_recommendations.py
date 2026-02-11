import asyncio
from collections import OrderedDict, defaultdict
from datetime import datetime
from itertools import chain
from typing import Counter, Iterable

from aiohttp import ClientSession
from pydantic import BaseModel
from sqlmodel import Session, select

from app.internal.audible.similar import list_similar_audible_books
from app.internal.models import Audiobook, AudiobookRequest, AudiobookWithRequests, User
from app.util.censor import censor
from app.util.log import logger


class AudiobookRecommendation(BaseModel):
    book: AudiobookWithRequests
    reason: str | None = None


class UserSimsRecommendation(BaseModel):
    recommendations: list[AudiobookRecommendation]
    total: int


class _BookScore(BaseModel):
    book: Audiobook
    score: float
    count: int
    avg_rank: float
    reason: str | None = None


class _RankedRecommendation(BaseModel):
    book: Audiobook
    rank: int


async def get_user_sims_recommendations(
    session: Session,
    client_session: ClientSession,
    user: User,
    seed_asins: Iterable[str] | None = None,
    limit: int = 10,
    offset: int = 0,
) -> UserSimsRecommendation:
    """
    Build personalized recommendations by aggregating Audible "similar" results
    for books the user has requested and optionally additional seed ASINs.

    Ranking:
    - Primary: frequency across all seed sims lists (higher is better)
    - Secondary: average position in sims lists (lower is better)

    Filters:
    - Exclude already requested by the user
    - Exclude already downloaded/owned (if detectable)
    - Exclude duplicates
    """

    # Collect user's requested books as default seeds
    user_requests = session.exec(
        select(Audiobook)
        .join(AudiobookRequest)
        .where(AudiobookRequest.user_username == user.username)
    ).all()

    # User preference profiles
    user_authors = Counter[str]()
    user_narrators = Counter[str]()
    for sim in user_requests:
        user_authors.update(sim.authors)
        user_narrators.update(sim.narrators)

    seeds = OrderedDict[str, None]()  # ordered set
    if seed_asins:
        seeds.update((asin, None) for asin in seed_asins)
    seeds.update((b.asin, None) for b in user_requests)

    if not seeds:
        logger.debug(
            "No seed ASINs for user recommendations",
            username=censor(user.username),
            input_seed_asins=seed_asins,
        )
        return UserSimsRecommendation(recommendations=[], total=0)

    async def _fetch(asin: str) -> list[_RankedRecommendation]:
        try:
            books = await list_similar_audible_books(session, client_session, asin)
            return [
                _RankedRecommendation(book=b, rank=idx) for idx, b in enumerate(books)
            ]
        except Exception as e:
            logger.debug("Fetch sims failed", asin=asin, error=str(e))
            return []

    books = await asyncio.gather(*[_fetch(asin) for asin in seeds])
    # flatten and extract input (seed) and requested asins
    # NOTE: this also filters out any books that have already been requested by the user
    similar_books = list(
        s for s in chain.from_iterable(books) if s.book.asin not in seeds
    )

    if not similar_books:
        logger.debug(
            "No sims found for user recommendations",
            username=censor(user.username),
            seed_asins=list(seeds.keys()),
        )
        return UserSimsRecommendation(recommendations=[], total=0)

    frequency = Counter[str]()
    positions = defaultdict[str, list[int]](list)
    for sim in similar_books:
        frequency[sim.book.asin] += 1
        positions[sim.book.asin].append(sim.rank)

    # Scoring weights
    W_FREQ = 10.0  # how often candidate appears across seeds
    W_RANK = 3.0  # audible average position (lower is better)
    W_AUTHOR_PREF = 1.2  # match with user's preferred authors
    W_NARR_PREF = 0.6  # match with user's preferred narrators
    W_RECENT = 0.5  # slight novelty for newer releases

    def _rank_component(avg_idx: float) -> float:
        # Convert average index to a 0..1 score (higher is better)
        return 1.0 / (1.0 + avg_idx)

    def _pref_component(names: list[str], pref_counter: Counter[str]) -> float:
        if not names:
            return 0.0
        return sum(pref_counter.get(n, 0) for n in names) / max(1.0, len(names))

    def _recent_component(b: Audiobook) -> float:
        try:
            age_days = max(0.0, (datetime.now() - b.release_date).days)
            # Newer books get up to ~1.0 bonus, decaying over ~2 years
            return max(0.0, 1.0 - (age_days / 730.0))
        except Exception:
            return 0.0

    # Build candidate score list
    candidate_scores: list[_BookScore] = []
    for sim in similar_books:
        if sim.book.downloaded:
            continue

        avg_pos = sum(positions[sim.book.asin]) / max(1, len(positions[sim.book.asin]))
        count = frequency[sim.book.asin]

        score = (
            W_FREQ * float(count)
            + W_RANK * _rank_component(avg_pos)
            + W_AUTHOR_PREF * _pref_component(sim.book.authors, user_authors)
            + W_NARR_PREF * _pref_component(sim.book.narrators, user_narrators)
            + W_RECENT * _recent_component(sim.book)
        )

        # Build human-readable reason
        reason_parts: list[str] = []
        if count > 0:
            reason_parts.append(f"similar to {count} of your books")
        if avg_pos < 3:
            reason_parts.append("highly ranked in Audible sims")
        elif avg_pos < 8:
            reason_parts.append("recommended by Audible sims")
        # Author/Narrator matches
        matched_authors = [
            a for a in (sim.book.authors or []) if user_authors.get(a, 0) > 0
        ]
        if matched_authors:
            # show up to 2
            reason_parts.append(
                "by your frequent author " + ", ".join(matched_authors[:2])
            )
        matched_narrs = [
            n for n in (sim.book.narrators or []) if user_narrators.get(n, 0) > 0
        ]
        if matched_narrs and not matched_authors:
            reason_parts.append("narrated by a favorite narrator")
        if _recent_component(sim.book) > 0.6:
            reason_parts.append("recent release")

        reason = (
            "; ".join(reason_parts)
            if reason_parts
            else "because you requested similar books"
        )
        candidate_scores.append(
            _BookScore(
                book=sim.book,
                score=score,
                count=count,
                avg_rank=avg_pos,
                reason=reason,
            )
        )

    candidate_scores.sort(key=lambda x: (-x.score, x.avg_rank, -x.count))

    # Diversity: limit over-repetition of same author in the top results (MMR-lite)
    MAX_PER_AUTHOR = 2
    author_counts = Counter[str]()
    diversified: list[_BookScore] = []
    remainder: list[_BookScore] = []
    added_asins = set[str]()
    for sim in candidate_scores:
        if sim.book.asin in added_asins:
            continue
        added_asins.add(sim.book.asin)
        authors = sim.book.authors or [""]
        # If any author exceeds cap, push to remainder; else accept
        if any(author_counts[a] >= MAX_PER_AUTHOR for a in authors if a):
            remainder.append(sim)
            continue
        for a in authors:
            if a:
                author_counts[a] += 1
        diversified.append(sim)

    ordered_books = diversified + remainder

    # Convert to BookSearchResult and apply limit
    results: list[AudiobookRecommendation] = []
    for sim in ordered_books[offset : offset + limit]:
        book_with_requests = AudiobookWithRequests(
            book=sim.book,
            requests=sim.book.requests,
            username=censor(user.username),
        )
        results.append(
            AudiobookRecommendation(
                book=book_with_requests,
                reason=sim.reason,
            )
        )

    return UserSimsRecommendation(recommendations=results, total=len(ordered_books))
