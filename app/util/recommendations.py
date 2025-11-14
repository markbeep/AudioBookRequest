"""
Recommendation engine utilities for generating book suggestions based on user activity and popularity.
"""

import asyncio
import time
import hashlib
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Optional, Iterable, Tuple, Dict, List

from aiohttp import ClientSession
import pydantic
from sqlalchemy import func
from sqlmodel import Session, col, desc, select

from app.internal.models import BookRequest, BookSearchResult, User

# Simple in-memory cache for per-user recommendation pools
class _UserRecsCacheKey(pydantic.BaseModel, frozen=True):
    username: str
    seed_sig: str  # compact signature of seeds


class _UserRecsCacheEntry(pydantic.BaseModel):
    value: list[BookSearchResult]
    reasons: dict[str, str] = {}
    timestamp: float


_USER_RECS_CACHE: dict[_UserRecsCacheKey, _UserRecsCacheEntry] = {}
_USER_RECS_TTL = 60 * 60 * 3  # 3 hours


async def get_user_sims_recommendations(
    session: Session,
    client_session: ClientSession,
    user: User,
    seed_asins: Optional[Iterable[str]] = None,
    limit: int = 12,
) -> list[BookSearchResult]:
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
    from app.internal.book_search import list_similar_audible_books
    from app.util.log import logger

    # Collect user's requested books as default seeds
    user_requests: list[BookRequest] = session.exec(
        select(BookRequest).where(BookRequest.user_username == user.username)
    ).all()
    user_seed_asins = [b.asin for b in user_requests if b.asin]

    # User preference profiles
    user_authors: Counter[str] = Counter()
    user_narrators: Counter[str] = Counter()
    for b in user_requests:
        user_authors.update(b.authors)
        user_narrators.update(b.narrators)

    seeds: list[str] = []
    if seed_asins:
        seeds.extend([s for s in seed_asins if s])
    seeds.extend(user_seed_asins)
    # Deduplicate while preserving order
    seen = set()
    seed_list: list[str] = []
    for a in seeds:
        if a not in seen:
            seen.add(a)
            seed_list.append(a)

    # If no seeds, fall back to simple personalized heuristic
    if not seed_list:
        return get_user_recommendations(session, user, limit)

    # Fetch sims for each seed concurrently (up to a reasonable cap)
    seed_list = seed_list[:20]  # cap to avoid excessive requests

    async def _fetch(asin: str):
        try:
            return await list_similar_audible_books(session, client_session, asin, num_results=50)
        except Exception:
            return []

    tasks = [
        _fetch(asin)
        for asin in seed_list
    ]

    all_sims_lists: list[list[BookRequest]] = []
    try:
        all_sims_lists = await asyncio.gather(*tasks)
    except Exception as e:
        logger.debug("Gather sims failed", error=str(e))

    # Aggregate by ASIN: count frequency and positions
    freq: Counter[str] = Counter()
    positions: defaultdict[str, list[int]] = defaultdict(list)
    book_map: dict[str, BookRequest] = {}

    for sims in all_sims_lists:
        for idx, b in enumerate(sims):
            if not b.asin:
                continue
            freq[b.asin] += 1
            positions[b.asin].append(idx)
            # Keep the first seen instance for map
            if b.asin not in book_map:
                book_map[b.asin] = b

    if not freq:
        # Fallback
        return get_user_recommendations(session, user, limit)

    # Build set of exclusions: already requested by user and downloaded
    user_requested_asins = {b.asin for b in user_requests}

    # Attempt to mark downloaded via ABS if configured (best-effort)
    try:
        from app.internal.audiobookshelf.config import abs_config
        from app.internal.audiobookshelf.client import abs_mark_downloaded_flags
        if abs_config.is_valid(session) and abs_config.get_check_downloaded(session):
            # Mark on a subset of candidates to avoid heavy calls
            subset = list(book_map.values())[:30]
            await abs_mark_downloaded_flags(session, client_session, subset)
    except Exception as e:
        logger.debug("ABS exist check skipped", error=str(e))

    # Scoring weights
    W_FREQ = 10.0         # how often candidate appears across seeds
    W_RANK = 3.0          # audible average position (lower is better)
    W_AUTHOR_PREF = 1.2   # match with user's preferred authors
    W_NARR_PREF = 0.6     # match with user's preferred narrators
    W_RECENT = 0.5        # slight novelty for newer releases

    def _rank_component(avg_idx: float) -> float:
        # Convert average index to a 0..1 score (higher is better)
        return 1.0 / (1.0 + avg_idx)

    def _pref_component(names: list[str], pref_counter: Counter[str]) -> float:
        if not names:
            return 0.0
        return sum(pref_counter.get(n, 0) for n in names) / max(1.0, len(names))

    def _recent_component(b: BookRequest) -> float:
        try:
            age_days = max(0.0, (datetime.now() - b.release_date).days)
            # Newer books get up to ~1.0 bonus, decaying over ~2 years
            return max(0.0, 1.0 - (age_days / 730.0))
        except Exception:
            return 0.0

    # Build candidate score list
    cand_scores: list[tuple[BookRequest, float, int, float]] = []
    reasons_map: dict[str, str] = {}
    for asin, count in freq.items():
        b = book_map.get(asin)
        if not b:
            continue
        if asin in user_requested_asins:
            continue
        if getattr(b, "downloaded", False):
            continue

        avg_pos = sum(positions[asin]) / max(1, len(positions[asin]))
        score = (
            W_FREQ * float(count)
            + W_RANK * _rank_component(avg_pos)
            + W_AUTHOR_PREF * _pref_component(b.authors, user_authors)
            + W_NARR_PREF * _pref_component(b.narrators, user_narrators)
            + W_RECENT * _recent_component(b)
        )
        cand_scores.append((b, score, count, avg_pos))

        # Build human-readable reason
        reason_parts: List[str] = []
        if count > 0:
            reason_parts.append(f"Similar to {count} of your books")
        if avg_pos < 3:
            reason_parts.append("highly ranked in Audible sims")
        elif avg_pos < 8:
            reason_parts.append("recommended by Audible sims")
        # Author/Narrator matches
        matched_authors = [a for a in (b.authors or []) if user_authors.get(a, 0) > 0]
        if matched_authors:
            # show up to 2
            reason_parts.append("by your frequent author " + ", ".join(matched_authors[:2]))
        matched_narrs = [n for n in (b.narrators or []) if user_narrators.get(n, 0) > 0]
        if matched_narrs and not matched_authors:
            reason_parts.append("narrated by a favorite narrator")
        if _recent_component(b) > 0.6:
            reason_parts.append("recent release")
        reasons_map[b.asin] = "; ".join(reason_parts) if reason_parts else "because you requested similar books"

    # Deterministic tiebreaker using username to keep results stable per user
    def _tie(b: BookRequest) -> int:
        h = hashlib.sha1(f"{user.username}:{b.asin}".encode(), usedforsecurity=False).hexdigest()
        return int(h[:8], 16)

    cand_scores.sort(key=lambda x: (-x[1], _tie(x[0])))

    # Diversity: limit over-repetition of same author in the top results (MMR-lite)
    MAX_PER_AUTHOR = 2
    author_counts: Counter[str] = Counter()
    diversified: list[BookRequest] = []
    remainder: list[BookRequest] = []
    for b, _score, _cnt, _avg in cand_scores:
        authors = b.authors or [""]
        # If any author exceeds cap, push to remainder; else accept
        if any(author_counts[a] >= MAX_PER_AUTHOR for a in authors if a):
            remainder.append(b)
            continue
        for a in authors:
            if a:
                author_counts[a] += 1
        diversified.append(b)

    ordered_books = diversified + remainder

    # Convert to BookSearchResult and apply limit
    results: list[BookSearchResult] = []
    for b in ordered_books[:limit]:
        r = BookSearchResult.model_validate(b)
        r.already_requested = False
        results.append(r)

    # Attach reasons to cache entry if pooled caller is used (handled upstream)
    return results


async def get_user_sims_recommendations_pooled(
    session: Session,
    client_session: ClientSession,
    user: User,
    seed_asins: Optional[Iterable[str]] = None,
    pool_size: int = 240,
) -> list[BookSearchResult]:
    """
    Return a larger, cached pool of personalized recommendations for a user.
    This supports pagination on the UI without re-aggregating for each page.
    """
    seeds_list = [s for s in (seed_asins or []) if s]

    # Build a deterministic, compact seed signature (limit to avoid huge keys)
    seed_sig = ",".join(sorted(seeds_list)[:60])
    cache_key = _UserRecsCacheKey(username=user.username, seed_sig=seed_sig)

    now = time.time()
    cached = _USER_RECS_CACHE.get(cache_key)
    if cached and now - cached.timestamp < _USER_RECS_TTL and len(cached.value) >= min(24, pool_size):
        return cached.value[:pool_size]
    try:
        # Compute detailed list again to capture reasons by reusing logic
        # Note: to avoid double work, we could refactor the sims aggregation, but keep it simple for now
        recs = await get_user_sims_recommendations(
            session=session,
            client_session=client_session,
            user=user,
            seed_asins=seeds_list,
            limit=pool_size,
        )
    except Exception:
        # Fallback to preference-based
        recs = get_user_recommendations(session, user, limit=pool_size)
    # Build a minimal reasons map from top-N (best-effort): generic reason
    reasons = {b.asin: "personalized mix from Audible sims and your history" for b in recs}

    _USER_RECS_CACHE[cache_key] = _UserRecsCacheEntry(value=recs, reasons=reasons, timestamp=now)
    return recs


async def get_user_sims_recommendations_pooled_with_reasons(
    session: Session,
    client_session: ClientSession,
    user: User,
    seed_asins: Optional[Iterable[str]] = None,
    pool_size: int = 240,
) -> tuple[list[BookSearchResult], dict[str, str]]:
    """
    Like get_user_sims_recommendations_pooled but also returns reasons map for display.
    """
    seeds_list = [s for s in (seed_asins or []) if s]
    seed_sig = ",".join(sorted(seeds_list)[:60])
    cache_key = _UserRecsCacheKey(username=user.username, seed_sig=seed_sig)
    now = time.time()
    cached = _USER_RECS_CACHE.get(cache_key)
    if cached and now - cached.timestamp < _USER_RECS_TTL and len(cached.value) >= min(24, pool_size):
        return cached.value[:pool_size], cached.reasons

    # Generate pool and attach generic reasons (as above)
    recs = await get_user_sims_recommendations_pooled(
        session, client_session, user, seed_asins=seeds_list, pool_size=pool_size
    )
    cached = _USER_RECS_CACHE.get(cache_key)
    reasons = cached.reasons if cached else {b.asin: "personalized recommendations" for b in recs}
    return recs, reasons
    _USER_RECS_CACHE[cache_key] = _UserRecsCacheEntry(value=recs, timestamp=now)
    return recs


def get_popular_books(
    session: Session, 
    limit: int = 12, 
    min_requests: int = 1,  # Lower default minimum
    exclude_downloaded: bool = True
) -> list[BookSearchResult]:
    """
    Get the most popular books based on how many users have requested them.
    
    Args:
        session: Database session
        limit: Maximum number of books to return
        min_requests: Minimum number of requests a book needs to be considered popular
        exclude_downloaded: Whether to exclude already downloaded books
    
    Returns:
        List of popular books as BookSearchResult objects
    """
    from app.util.log import logger
    
    # First check if there are any book requests at all
    total_requests = session.exec(
        select(func.count()).select_from(BookRequest).where(
            col(BookRequest.user_username).is_not(None)
        )
    ).one()
    
    logger.debug(f"Total book requests in database: {total_requests}")
    
    if total_requests == 0:
        logger.debug("No user requests found, returning empty list")
        return []
    
    query = (
        select(
            BookRequest,
            func.count(BookRequest.user_username).label("request_count")
        )
        .where(
            col(BookRequest.user_username).is_not(None),  # Only count actual user requests
        )
        .group_by(BookRequest.asin)
        .having(func.count(BookRequest.user_username) >= min_requests)
        .order_by(desc("request_count"), desc(BookRequest.updated_at))
        .limit(limit)
    )
    
    if exclude_downloaded:
        query = query.where(~BookRequest.downloaded)
    
    results = session.exec(query).all()
    
    logger.debug(f"Popular books query returned {len(results)} results")
    
    popular_books = []
    for book, request_count in results:
        book_result = BookSearchResult.model_validate(book)
        book_result.already_requested = True  # These are popular because they were requested
        popular_books.append(book_result)
        logger.debug(f"Popular book: {book.title} (requests: {request_count})")
    
    return popular_books


def get_recently_requested_books(
    session: Session, 
    limit: int = 12, 
    days_back: int = 30,
    exclude_downloaded: bool = True
) -> list[BookSearchResult]:
    """
    Get recently requested books within the specified time frame.
    
    Args:
        session: Database session
        limit: Maximum number of books to return
        days_back: How many days back to look for recent requests
        exclude_downloaded: Whether to exclude already downloaded books
    
    Returns:
        List of recently requested books as BookSearchResult objects
    """
    cutoff_date = datetime.now() - timedelta(days=days_back)
    
    query = (
        select(BookRequest)
        .where(
            col(BookRequest.user_username).is_not(None),
            BookRequest.updated_at >= cutoff_date,
        )
        .order_by(desc(BookRequest.updated_at))
        .limit(limit * 2)  # Get more to account for duplicates
    )
    
    if exclude_downloaded:
        query = query.where(~BookRequest.downloaded)
    
    results = session.exec(query).all()
    
    # Remove duplicates by ASIN while preserving order
    seen_asins = set()
    recent_books = []
    
    for book in results:
        if book.asin not in seen_asins and len(recent_books) < limit:
            seen_asins.add(book.asin)
            book_result = BookSearchResult.model_validate(book)
            book_result.already_requested = True
            recent_books.append(book_result)
    
    return recent_books


def get_books_by_popular_authors(
    session: Session, 
    limit: int = 12,
    exclude_downloaded: bool = True
) -> list[BookSearchResult]:
    """
    Get books by the most popular authors (authors with the most requested books).
    
    Args:
        session: Database session
        limit: Maximum number of books to return
        exclude_downloaded: Whether to exclude already downloaded books
    
    Returns:
        List of books by popular authors as BookSearchResult objects
    """
    # First, get the most popular authors
    all_requests = session.exec(
        select(BookRequest).where(
            col(BookRequest.user_username).is_not(None),
        )
    ).all()
    
    # Count requests per author
    author_request_counts = Counter()
    for book in all_requests:
        for author in book.authors:
            author_request_counts[author] += 1
    
    # Get top authors
    top_authors = [author for author, _ in author_request_counts.most_common(10)]
    
    if not top_authors:
        return []
    
    # Get books by these popular authors that haven't been requested yet
    query = (
        select(BookRequest)
        .where(
            col(BookRequest.user_username).is_(None),  # Only cache entries, not user requests
        )
        .order_by(desc(BookRequest.updated_at))
    )
    
    if exclude_downloaded:
        query = query.where(~BookRequest.downloaded)
    
    cache_books = session.exec(query).all()
    
    # Filter books by popular authors
    author_books = []
    for book in cache_books:
        if len(author_books) >= limit:
            break
        
        # Check if any of the book's authors are in our popular authors list
        if any(author in top_authors for author in book.authors):
            book_result = BookSearchResult.model_validate(book)
            book_result.already_requested = False
            author_books.append(book_result)
    
    return author_books


def get_user_recommendations(
    session: Session, 
    user: User, 
    limit: int = 12
) -> list[BookSearchResult]:
    """
    Get personalized recommendations for a specific user based on their request history.
    
    Args:
        session: Database session
        user: User to get recommendations for
        limit: Maximum number of books to return
    
    Returns:
        List of recommended books for the user
    """
    # Get user's requested books to analyze preferences
    user_requests = session.exec(
        select(BookRequest).where(
            BookRequest.user_username == user.username
        )
    ).all()
    
    if not user_requests:
        # If user has no history, return popular books
        return get_popular_books(session, limit)
    
    # Extract user's favorite authors and narrators
    user_authors = []
    user_narrators = []
    
    for book in user_requests:
        user_authors.extend(book.authors)
        user_narrators.extend(book.narrators)
    
    # Count preferences
    author_preferences = Counter(user_authors)
    narrator_preferences = Counter(user_narrators)
    
    # Get books from cache that match user preferences
    cache_books = session.exec(
        select(BookRequest).where(
            col(BookRequest.user_username).is_(None),  # Cache entries only
            ~BookRequest.downloaded
        )
        .order_by(desc(BookRequest.updated_at))
        .limit(limit * 5)  # Get more to filter from
    ).all()
    
    # Score books based on user preferences
    scored_books = []
    user_requested_asins = {book.asin for book in user_requests}
    
    for book in cache_books:
        if book.asin in user_requested_asins:
            continue  # Skip books user already requested
        
        score = 0
        
        # Score based on favorite authors
        for author in book.authors:
            score += author_preferences.get(author, 0) * 3
        
        # Score based on favorite narrators
        for narrator in book.narrators:
            score += narrator_preferences.get(narrator, 0) * 2
        
        if score > 0:
            book_result = BookSearchResult.model_validate(book)
            book_result.already_requested = False
            scored_books.append((book_result, score))
    
    # Sort by score and return top results
    scored_books.sort(key=lambda x: x[1], reverse=True)
    return [book for book, _ in scored_books[:limit]]


async def get_popular_books_from_audible(
    session: Session,
    client_session: ClientSession,
    limit: int = 12
) -> list[BookSearchResult]:
    """
    Get popular books directly from Audible's API.
    """
    from app.internal.book_search import list_popular_audible_books
    from app.util.log import logger
    
    try:
        popular_books = await list_popular_audible_books(
            session=session,
            client_session=client_session, 
            num_results=limit
        )
        
        result_books = []
        for book in popular_books:
            book_result = BookSearchResult.model_validate(book)
            book_result.already_requested = False
            result_books.append(book_result)
        
        logger.debug(f"Retrieved {len(result_books)} popular books from Audible")
        return result_books
        
    except Exception as e:
        logger.error(f"Failed to get popular books from Audible: {e}")
        return []


async def get_category_books(
    session: Session,
    client_session: ClientSession,
    search_terms: list[str],
    limit: int = 12
) -> list[BookSearchResult]:
    """Get books for a specific category using search terms."""
    from app.internal.book_search import list_audible_books
    from app.util.log import logger
    
    all_books = []
    books_per_term = max(1, limit // len(search_terms))
    
    for term in search_terms:
        try:
            term_books = await list_audible_books(
                session=session,
                client_session=client_session,
                query=term,
                num_results=books_per_term + 2,  # Get a few extra to account for duplicates
                page=0
            )
            
            # Add unique books only
            for book in term_books:
                book_result = BookSearchResult.model_validate(book)
                book_result.already_requested = False
                
                # Check if already exists (by ASIN)
                if not any(existing.asin == book_result.asin for existing in all_books):
                    all_books.append(book_result)
                
                if len(all_books) >= limit:
                    break
                    
        except Exception as e:
            logger.warning(f"Failed to search for category term '{term}': {e}")
            continue
        
        if len(all_books) >= limit:
            break
    
    return all_books[:limit]


async def get_homepage_recommendations_async(
    session: Session, 
    client_session: ClientSession,
    user: Optional[User] = None,
    abs_seed_asins: Optional[Iterable[str]] = None,
    include_ai: bool = True,
) -> dict[str, list[BookSearchResult]]:
    """
    Get a comprehensive set of Netflix-style recommendations for the homepage.
    
    Args:
        session: Database session
        client_session: HTTP client session
        user: Optional user for personalized recommendations
    
    Returns:
        Dictionary with different recommendation categories
    """
    from app.util.log import logger
    
    recommendations = {}
    
    # 1. Popular books (mix of user requests and Audible popular)
    user_popular = get_popular_books(session, limit=6)
    audible_popular = await get_popular_books_from_audible(session, client_session, limit=12)
    
    # Combine and remove duplicates
    popular_combined = list(user_popular)
    for book in audible_popular:
        if not any(existing.asin == book.asin for existing in popular_combined):
            popular_combined.append(book)
    recommendations["popular"] = popular_combined[:12]
    
    # 2. User personalized recommendations (if user exists)
    if user:
        # Build seed list from optional ABS items
        seed_asins: list[str] = []
        if abs_seed_asins:
            seed_asins = [a for a in abs_seed_asins if a]
        try:
            # Use pooled generator to keep results stable and rich
            rec_pool = await get_user_sims_recommendations_pooled(
                session, client_session, user, seed_asins, pool_size=60
            )
            recommendations["for_you"] = rec_pool[:12]
        except Exception as e:
            logger.warning(f"Sims-based recommendations failed, falling back: {e}")
            recommendations["for_you"] = get_user_recommendations(session, user, limit=12)

        # 2b. Because you've read sections (seeded by user's recent requests)
        try:
            sections: list[dict] = []
            # Fetch recent requested books by user to use as seeds
            recent_reqs: list[BookRequest] = session.exec(
                select(BookRequest)
                .where(BookRequest.user_username == user.username)
                .order_by(desc(BookRequest.updated_at))
                .limit(12)
            ).all()
            # Deduplicate by ASIN and keep those with ASINs
            seen_asins: set[str] = set()
            seeds: list[BookRequest] = []
            for b in recent_reqs:
                if b.asin and b.asin not in seen_asins:
                    seen_asins.add(b.asin)
                    seeds.append(b)
                if len(seeds) >= 3:
                    break
            # For each seed, fetch similar books
            from app.internal.book_search import list_similar_audible_books
            for seed in seeds:
                try:
                    sims = await list_similar_audible_books(session, client_session, seed.asin, num_results=24)
                except Exception:
                    sims = []
                books: list[BookSearchResult] = []
                for sb in sims:
                    try:
                        r = BookSearchResult.model_validate(sb)
                        r.already_requested = False
                        # Avoid including the seed itself if it appears
                        if r.asin and r.asin != seed.asin and not any(x.asin == r.asin for x in books):
                            books.append(r)
                    except Exception:
                        continue
                if books:
                    sections.append({
                        "title": f"Because you read {seed.title}",
                        "description": None,
                        "books": books[:12],
                    })
            if sections:
                # Expose as structured sections for homepage rendering
                recommendations["because_you_read_sections"] = sections  # type: ignore
        except Exception as e:
            logger.debug("Because-you-read sections failed", error=str(e))

        # 2c. Authors you like (top authors from history)
        try:
            # Count authors from user's requests
            user_requests: list[BookRequest] = session.exec(
                select(BookRequest).where(BookRequest.user_username == user.username)
            ).all()
            author_counts: Counter[str] = Counter()
            for b in user_requests:
                for a in b.authors or []:
                    author_counts[a] += 1
            top_authors = [a for a, _ in author_counts.most_common(5) if a]
            author_sections: list[dict] = []
            for a in top_authors[:2]:
                try:
                    # Use author name as search term; fetch a compact list
                    books = await get_category_books(session, client_session, [a], limit=12)
                except Exception:
                    books = []
                if books:
                    author_sections.append({
                        "title": f"More by {a}",
                        "description": None,
                        "books": books,
                    })
            if author_sections:
                recommendations["authors_you_like_sections"] = author_sections  # type: ignore
        except Exception as e:
            logger.debug("Authors-you-like sections failed", error=str(e))
    
    # 3. Recently requested by community
    recommendations["recent"] = get_recently_requested_books(session, limit=12)
    
    # 4. Category-based recommendations (run in parallel for speed)
    categories = {
        "trending": ["trending", "viral", "popular now", "hot"],
        "business": ["business", "entrepreneurship", "leadership", "productivity", "success"],
        "fiction": ["fiction", "novel", "literature", "story", "fantasy", "mystery"],
        "biography": ["biography", "memoir", "autobiography", "life story", "history"],
        "science": ["science", "technology", "physics", "psychology", "innovation"],
        "recent_releases": ["2024", "new release", "latest", "just released"]
    }
    
    # Create tasks for parallel execution
    category_tasks = []
    for category_name, search_terms in categories.items():
        task = get_category_books(session, client_session, search_terms, limit=12)
        category_tasks.append((category_name, task))
    
    # Execute category searches in parallel
    try:
        for category_name, task in category_tasks:
            try:
                category_books = await task
                recommendations[category_name] = category_books
                logger.debug(f"Retrieved {len(category_books)} books for {category_name}")
            except Exception as e:
                logger.warning(f"Failed to get {category_name} books: {e}")
                recommendations[category_name] = []
    except Exception as e:
        logger.error(f"Error in category recommendations: {e}")
    
    # 5. AI-powered category (best-effort) — optionally included to avoid blocking initial page render
    if include_ai:
        try:
            from app.internal.ai.config import ai_config
            from app.internal.ai.client import fetch_ai_categories, fetch_ai_book_recommendations
            if ai_config.is_configured(session):
                ai_categories = await fetch_ai_categories(session, client_session, user, desired_count=3)
                ai_sections: list[dict] = []
                if ai_categories:
                    for cat in ai_categories:
                        title = cat.get("title") or "AI Picks"
                        desc = cat.get("description") or ""
                        terms = cat.get("search_terms") or []
                        try:
                            books = await get_category_books(session, client_session, terms, limit=12)
                        except Exception:
                            books = []
                        ai_sections.append({"title": title, "description": desc, "books": books})
                    if ai_sections:
                        # Backward-compatible top section
                        recommendations["ai_picks"] = ai_sections[0]["books"]
                        recommendations["ai_picks_title"] = ai_sections[0]["title"]  # type: ignore
                        # Full structured sections
                        recommendations["ai_sections"] = ai_sections  # type: ignore

                # AI title-level recs: "Because you liked" with reasons
                ai_title_recs = await fetch_ai_book_recommendations(session, client_session, user, desired_count=12)
                if ai_title_recs:
                    # Resolve to actual BookSearchResults via searches
                    resolved: list[dict] = []
                    seen_asins: set[str] = set()
                    user_asins: set[str] = set()
                    if user:
                        user_asins = {b.asin for b in session.exec(select(BookRequest).where(BookRequest.user_username == user.username)).all() if b.asin}
                    for rec in ai_title_recs:
                        # Build search candidates: explicit terms or title+author
                        terms = rec.get("search_terms") or []
                        if not terms:
                            t = rec.get("title") or ""
                            a = rec.get("author") or ""
                            if t:
                                q = f"{t} {a}".strip()
                                terms = [q]
                        books: list[BookSearchResult] = []
                        if terms:
                            try:
                                books = await get_category_books(session, client_session, terms, limit=3)
                            except Exception:
                                books = []
                        # Pick best candidate by title/author match
                        picked: Optional[BookSearchResult] = None
                        if books:
                            target_title = (rec.get("title") or "").lower().strip()
                            target_author = (rec.get("author") or "").lower().strip()
                            for b in books:
                                bt = (b.title or "").lower().strip()
                                auths = ",".join(a.lower() for a in (b.authors or []))
                                if target_title and target_title in bt and (not target_author or target_author in auths):
                                    picked = b
                                    break
                            if not picked:
                                picked = books[0]
                        if picked and picked.asin and picked.asin not in seen_asins and picked.asin not in user_asins:
                            seen_asins.add(picked.asin)
                            reason_seed = rec.get("seed_title") or "something you liked"
                            reason_txt = rec.get("reasoning") or "similar to your taste"
                            resolved.append({
                                "book": picked,
                                "reason": f"Because you liked {reason_seed}: {reason_txt}",
                            })
                    if resolved:
                        recommendations["ai_because_you_like"] = resolved  # type: ignore
        except Exception as e:
            # Swallow errors; AI is optional but surface at info level
            from app.util.log import logger
            logger.info("AI category generation failed", error=str(e))

    # Log summary
    total_books = sum(len(books) for books in recommendations.values() if isinstance(books, list))
    logger.info(f"Generated {len(recommendations)} categories with {total_books} total books")
    
    return recommendations


def get_homepage_recommendations(
    session: Session, 
    user: Optional[User] = None
) -> dict[str, list[BookSearchResult]]:
    """
    Get a comprehensive set of recommendations for the homepage (sync version - fallback).
    
    Args:
        session: Database session
        user: Optional user for personalized recommendations
    
    Returns:
        Dictionary with different recommendation categories
    """
    from app.util.log import logger
    
    recommendations = {}
    
    # Always include popular books
    recommendations["popular"] = get_popular_books(session, limit=8)
    
    # Include recently requested books
    recommendations["recent"] = get_recently_requested_books(session, limit=8)
    
    # If user is provided, add personalized recommendations
    if user:
        recommendations["for_you"] = get_user_recommendations(session, user, limit=8)
    else:
        # If no user, show books by popular authors instead
        recommendations["by_popular_authors"] = get_books_by_popular_authors(session, limit=8)
    
    # If we have no recommendations at all, fall back to showing any cached books
    total_recs = sum(len(books) for books in recommendations.values())
    logger.debug(f"Total recommendations: {total_recs}")
    
    if total_recs == 0:
        logger.debug("No user-based recommendations found, checking for cached books")
        
        # Get any cached books from search results
        cached_books = session.exec(
            select(BookRequest)
            .where(col(BookRequest.user_username).is_(None))  # These are cache entries
            .order_by(desc(BookRequest.updated_at))
            .limit(16)
        ).all()
        
        logger.debug(f"Found {len(cached_books)} cached books")
        
        if cached_books:
            fallback_books = []
            for book in cached_books[:8]:
                book_result = BookSearchResult.model_validate(book)
                book_result.already_requested = False
                fallback_books.append(book_result)
            recommendations["popular"] = fallback_books
            logger.debug(f"Using {len(fallback_books)} cached books as popular recommendations")
        else:
            logger.debug("No cached books found either - database appears empty")
            
            # Check total book entries in database
            total_books = session.exec(select(func.count()).select_from(BookRequest)).one()
            logger.debug(f"Total BookRequest entries in database: {total_books}")
    
    return recommendations