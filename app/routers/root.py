import hashlib
from os import PathLike
from pathlib import Path
from typing import Annotated, Callable
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, Security
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import func
from sqlmodel import Session, col, select

from app.internal.auth.authentication import (
    ABRAuth,
    DetailedUser,
    create_user,
    raise_for_invalid_password,
)
from app.internal.auth.config import auth_config
from app.internal.auth.login_types import LoginTypeEnum
from app.internal.env_settings import Settings
from app.internal.models import BookRequest, GroupEnum, BookSearchResult
from aiohttp import ClientSession
from app.util.connection import get_connection
from app.util.db import get_session
from app.util.log import logger
from app.util.redirect import BaseUrlRedirectResponse
from app.util.recommendations import (
    get_homepage_recommendations,
    get_homepage_recommendations_async,
    get_user_sims_recommendations,
    get_user_sims_recommendations_pooled,
    get_user_sims_recommendations_pooled_with_reasons,
)
from app.internal.audiobookshelf.config import abs_config
from app.internal.audiobookshelf.client import abs_list_library_items
from app.util.templates import template_response, templates
from app.internal.book_search import list_audible_books, get_region_from_settings
from app.internal.ai.client import clear_ai_cache_for_user

router = APIRouter()


root = Path("static")

etag_cache: dict[PathLike[str] | str, str] = {}


# Pick a fun, consistent emoji based on an AI category title
def pick_category_emoji(title: str) -> str:
    t = (title or "").lower()
    # Order matters: first match wins
    mapping: list[tuple[list[str], str]] = [
        (["productivity", "habit", "focus", "self-improve", "motivation"], "🌱"),
        (["business", "startup", "entrepreneur", "management", "leadership"], "💼"),
        (["finance", "invest", "money", "wealth", "economics"], "💰"),
        (["science", "physics", "chemistry", "biology", "space", "neuroscience"], "🔬"),
        (["psychology", "mind", "behavior", "cognitive"], "🧠"),
        (["technology", "programming", "software", "ai", "machine learning"], "🖥️"),
        (["history", "histor", "ancient", "civilization"], "🏺"),
        (["biography", "memoir", "autobiography"], "👤"),
        (["fiction", "novel", "literature"], "📖"),
        (["fantasy", "dragon", "magic"], "🧙"),
        (["mystery", "detective", "crime", "thriller"], "🕵️"),
        (["horror", "ghost", "haunted"], "👻"),
        (["romance", "love", "relationship"], "💞"),
        (["education", "learn", "course", "study"], "🎓"),
        (["kids", "children", "ya", "young adult"], "🎈"),
        (["new", "recent", "release", "latest"], "🆕"),
        (["trend", "popular", "hot"], "📈"),
        (["audio", "narration", "audiobook"], "🎧"),
    ]
    for keywords, emoji in mapping:
        for k in keywords:
            if k in t:
                return emoji
    return "🤖"  # default/fallback for AI picks


def add_cache_headers(func: Callable[..., FileResponse]):
    def wrapper(v: str):
        file = func()
        if not (etag := etag_cache.get(file.path)) or Settings().app.debug:
            with open(file.path, "rb") as f:
                etag = hashlib.sha1(f.read(), usedforsecurity=False).hexdigest()
            etag_cache[file.path] = etag

        file.headers.append("Etag", etag)
        # cache for a year. All static files should do cache busting with `?v=<version>`
        file.headers.append("Cache-Control", f"public, max-age={60 * 60 * 24 * 365}")
        return file

    return wrapper


@router.get("/static/globals.css")
@add_cache_headers
def read_globals_css():
    return FileResponse(root / "globals.css", media_type="text/css")


@router.get("/static/nouislider.css")
@add_cache_headers
def read_nouislider_css():
    return FileResponse(root / "nouislider.min.css", media_type="text/css")


@router.get("/static/nouislider.js")
@add_cache_headers
def read_nouislider_js():
    return FileResponse(root / "nouislider.min.js", media_type="text/javascript")


@router.get("/static/apple-touch-icon.png")
@add_cache_headers
def read_apple_touch_icon():
    return FileResponse(root / "apple-touch-icon.png", media_type="image/png")


@router.get("/static/favicon-32x32.png")
@add_cache_headers
def read_favicon_32():
    return FileResponse(root / "favicon-32x32.png", media_type="image/png")


@router.get("/static/favicon-16x16.png")
@add_cache_headers
def read_favicon_16():
    return FileResponse(root / "favicon-16x16.png", media_type="image/png")


@router.get("/static/site.webmanifest")
@add_cache_headers
def read_site_webmanifest():
    """Serve a manifest with correct base paths and names for PWA installability."""
    base = Settings().app.base_url.rstrip("/") or ""
    version = Settings().app.version
    manifest = {
        "name": "AudioBookRequest",
        "short_name": "ABR",
        # start_url should include base to work behind subpaths
        "start_url": f"{base}/",  # resolved by the browser to absolute path
        "scope": f"{base}/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#ffffff",
        "icons": [
            {
                "src": f"{base}/static/android-chrome-192x192.png?v={version}",
                "sizes": "192x192",
                "type": "image/png",
            },
            {
                "src": f"{base}/static/android-chrome-512x512.png?v={version}",
                "sizes": "512x512",
                "type": "image/png",
            },
        ],
    }
    return JSONResponse(manifest, media_type="application/manifest+json")


@router.get("/service-worker.js")
@add_cache_headers
def read_service_worker():
    """Service worker served from app root for proper scope control."""
    return FileResponse(root / "service-worker.js", media_type="application/javascript")


@router.get("/static/htmx.js")
@add_cache_headers
def read_htmx():
    return FileResponse(root / "htmx.js", media_type="text/javascript")


@router.get("/static/htmx-preload.js")
@add_cache_headers
def read_htmx_preload():
    return FileResponse(root / "htmx-preload.js", media_type="text/javascript")


@router.get("/static/alpine.js")
@add_cache_headers
def read_alpinejs():
    return FileResponse(root / "alpine.js", media_type="text/javascript")


@router.get("/static/toastify.js")
@add_cache_headers
def read_toastifyjs():
    return FileResponse(root / "toastify.js", media_type="text/javascript")


@router.get("/static/toastify.css")
@add_cache_headers
def read_toastifycss():
    return FileResponse(root / "toastify.css", media_type="text/css")


@router.get("/static/favicon.svg")
@add_cache_headers
def read_favicon_svg():
    return FileResponse(root / "favicon.svg", media_type="image/svg+xml")


@router.get("/")
async def read_root(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: DetailedUser = Security(ABRAuth()),
):
    # If ABS is configured, fetch a slice of the user's ABS library to show and seed personalized recs
    abs_library: list[BookRequest] | None = None
    try:
        if abs_config.is_valid(session) and abs_config.get_library_id(session):
            abs_library = await abs_list_library_items(session, client_session, limit=12)
    except Exception as e:
        logger.debug("ABS: fetching library for homepage failed", error=str(e))

    # Get recommendations for the homepage (pass ABS ASINs as seeds for personalization)
    try:
        abs_seeds = [b.asin for b in (abs_library or []) if b.asin]
        # Enrich missing ASINs from ABS by searching Audible by title + first author
        missing_seed_candidates = [b for b in (abs_library or []) if not b.asin]
        if missing_seed_candidates:
            region = get_region_from_settings()
            for b in missing_seed_candidates[:8]:  # cap lookups
                try:
                    q = f"{b.title} {b.authors[0] if b.authors else ''}".strip()
                    if not q:
                        continue
                    results = await list_audible_books(
                        session=session,
                        client_session=client_session,
                        query=q,
                        num_results=1,
                        page=0,
                        audible_region=region,
                    )
                    if results:
                        seed_asin = results[0].asin
                        if seed_asin and seed_asin not in abs_seeds:
                            abs_seeds.append(seed_asin)
                except Exception as ie:
                    logger.debug("ABS seed ASIN lookup failed", title=b.title, error=str(ie))
        # Important: do not include AI in initial render to avoid blocking page load
        recommendations = await get_homepage_recommendations_async(
            session, client_session, user, abs_seed_asins=abs_seeds, include_ai=False
        )
    except Exception as e:
        logger.warning(f"Failed to get async recommendations, falling back to sync: {e}")
        recommendations = get_homepage_recommendations(session, user)
    
    # Debug: Log what recommendations we got
    category_counts = {
        category: len(books) for category, books in recommendations.items()
    }
    logger.debug("Homepage recommendations", **category_counts)
    
    return template_response(
        "root.html",
        request,
        user,
        {
            "recommendations": recommendations,
            "abs_library": abs_library or [],
        },
    )


@router.get("/recommendations/for-you")
async def read_for_you(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    page: int = 1,
    per_page: int = 24,
    user: DetailedUser = Security(ABRAuth()),
):
    """Full page of personalized recommendations with simple pagination."""
    # Clamp pagination values
    page = max(1, page)
    per_page = max(6, min(60, per_page))

    # Seed from ABS like on homepage (including resolving missing ASINs)
    abs_seeds: list[str] = []
    try:
        abs_library: list[BookRequest] | None = None
        if abs_config.is_valid(session) and abs_config.get_library_id(session):
            abs_library = await abs_list_library_items(session, client_session, limit=24)
            abs_seeds.extend([b.asin for b in (abs_library or []) if b.asin])

            # Resolve some missing ASINs
            missing = [b for b in (abs_library or []) if not b.asin][:10]
            if missing:
                region = get_region_from_settings()
                for b in missing:
                    q = f"{b.title} {b.authors[0] if b.authors else ''}".strip()
                    if not q:
                        continue
                    try:
                        res = await list_audible_books(
                            session=session,
                            client_session=client_session,
                            query=q,
                            num_results=1,
                            page=0,
                            audible_region=region,
                        )
                        if res and res[0].asin and res[0].asin not in abs_seeds:
                            abs_seeds.append(res[0].asin)
                    except Exception as ie:
                        logger.debug("ABS seed resolve failed", title=b.title, error=str(ie))
    except Exception as e:
        logger.debug("ABS seeding skipped", error=str(e))

    # Fetch a larger pool to support pagination
    # Fetch a larger pooled list once and slice
    try:
        full_list, reasons = await get_user_sims_recommendations_pooled_with_reasons(
            session, client_session, user, seed_asins=abs_seeds, pool_size=240
        )
    except Exception as e:
        logger.warning("For You full-page recs failed, falling back", error=str(e))
        # Fall back to preference-based recs
        from app.util.recommendations import get_user_recommendations
        full_list = get_user_recommendations(session, user, limit=240)
        reasons = {b.asin: "personalized recommendations" for b in full_list}

    # Paginate
    start = (page - 1) * per_page
    end = start + per_page
    page_items = full_list[start:end]
    total_items = len(full_list)
    has_next = end < total_items

    return template_response(
        "recommendations/for_you.html",
        request,
        user,
        {
            "books": page_items,
            "page": page,
            "per_page": per_page,
            "has_next": has_next,
            "total_items": total_items,
            "reasons": reasons,
        },
    )


@router.get("/recommendations/ai")
async def read_ai_page(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    refresh: bool = False,
    user: DetailedUser = Security(ABRAuth()),
):
    # Optionally bypass cache when refresh=true
    if refresh:
        clear_ai_cache_for_user(user)
        logger.info("AI page refresh requested; cache cleared", username=user.username)

    # Render lightweight shell; sections will be loaded asynchronously via HTMX
    return template_response(
        "recommendations/ai.html",
        request,
        user,
        {
            "sections": [],
            "title": "AI Picks",
            "description": None,
        },
    )


@router.post("/recommendations/ai/refresh")
def refresh_ai_recommendations(
    session: Annotated[Session, Depends(get_session)],
    user: DetailedUser = Security(ABRAuth()),
):
    clear_ai_cache_for_user(user)
    return Response(status_code=204, headers={"HX-Refresh": "true"})


# Lightweight fragment endpoints to fetch AI-powered sections without blocking initial page
@router.get("/recommendations/ai/home-fragment")
async def ai_home_fragment(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: DetailedUser = Security(ABRAuth()),
):
    from app.internal.ai.config import ai_config
    from app.internal.ai.client import fetch_ai_categories, fetch_ai_book_recommendations
    from app.util.recommendations import get_category_books

    context: dict = {}
    if ai_config.is_configured(session):
        # AI discovery sections
        ai_sections: list[dict] = []
        try:
            cats = await fetch_ai_categories(session, client_session, user, desired_count=3)
        except Exception:
            cats = None
        if cats:
            for cat in cats:
                title = cat.get("title") or "AI Picks"
                desc = cat.get("description") or ""
                terms = cat.get("search_terms") or []
                try:
                    books = await get_category_books(session, client_session, terms, limit=12)
                except Exception:
                    books = []
                ai_sections.append({
                    "title": title,
                    "description": desc,
                    "books": books,
                    "emoji": pick_category_emoji(title),
                })
        if ai_sections:
            context["ai_sections"] = ai_sections
            context["ai_picks_title"] = ai_sections[0]["title"]
            context["ai_picks"] = ai_sections[0]["books"]

        # Because you liked — title-level AI recs
        try:
            title_recs = await fetch_ai_book_recommendations(session, client_session, user, desired_count=12)
        except Exception:
            title_recs = None
        if title_recs:
            # Resolve to concrete books similarly to util
            resolved: list[dict] = []
            seen_asins: set[str] = set()
            user_asins: set[str] = set()
            if user:
                user_asins = {b.asin for b in session.exec(select(BookRequest).where(BookRequest.user_username == user.username)).all() if b.asin}
            for rec in title_recs:
                terms = rec.get("search_terms") or []
                if not terms:
                    t = rec.get("title") or ""
                    a = rec.get("author") or ""
                    if t:
                        terms = [f"{t} {a}".strip()]
                books: list[BookSearchResult] = []
                if terms:
                    try:
                        books = await get_category_books(session, client_session, terms, limit=3)
                    except Exception:
                        books = []
                picked: BookSearchResult | None = None
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
                    resolved.append({"book": picked, "reason": f"Because you liked {reason_seed}: {reason_txt}"})
            if resolved:
                context["ai_because_you_like"] = resolved

    # Render the fragment (will be swapped into the homepage)
    return templates.TemplateResponse(
        "components/ai_home_sections.html",
        {"request": request, **context},
    )


@router.get("/recommendations/ai/page-fragment")
async def ai_page_fragment(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: DetailedUser = Security(ABRAuth()),
):
    from app.internal.ai.config import ai_config
    from app.internal.ai.client import fetch_ai_categories
    from app.util.recommendations import get_category_books

    title: str = "AI Picks"
    description: str | None = None
    sections: list[dict] = []
    if ai_config.is_configured(session):
        try:
            cats = await fetch_ai_categories(session, client_session, user, desired_count=3)
        except Exception:
            cats = None
        if cats:
            for cat in cats:
                t = cat.get("title") or "AI Picks"
                d = cat.get("description") or ""
                terms = cat.get("search_terms") or []
                try:
                    books = await get_category_books(session, client_session, terms, limit=24)
                except Exception:
                    books = []
                sections.append({
                    "title": t,
                    "description": d,
                    "books": books,
                    "emoji": pick_category_emoji(t),
                })
            if sections:
                title = sections[0]["title"]
                description = sections[0]["description"]
    return templates.TemplateResponse(
        "components/ai_page_sections.html",
        {"request": request, "sections": sections, "title": title, "description": description},
    )


 


@router.get("/init")
def read_init(request: Request, session: Annotated[Session, Depends(get_session)]):
    init_username = Settings().app.init_root_username.strip()
    init_password = Settings().app.init_root_password.strip()

    try:
        login_type = Settings().app.get_force_login_type()
        if login_type == LoginTypeEnum.oidc and (
            not init_username.strip() or not init_password.strip()
        ):
            raise ValueError(
                "OIDC login type is not supported for initial setup without an initial username/password."
            )
    except ValueError as e:
        logger.error(f"Invalid force login type: {e}")
        login_type = None

    if init_username and init_password:
        logger.info(
            "Initial root credentials provided. Skipping init page.",
            username=init_username,
            login_type=login_type,
        )
        if not login_type:
            logger.warning(
                "No login type set. Defaulting to 'forms'.", username=init_username
            )
            login_type = LoginTypeEnum.forms

        user = create_user(init_username, init_password, GroupEnum.admin, root=True)
        session.add(user)
        auth_config.set_login_type(session, login_type)
        session.commit()
        return BaseUrlRedirectResponse("/")

    elif init_username or init_password:
        logger.warning(
            "Initial root credentials provided but missing either username or password. Skipping initialization through environment variables.",
            set_username=bool(init_username),
            set_password=bool(init_password),
        )

    return templates.TemplateResponse(
        "init.html",
        {
            "request": request,
            "hide_navbar": True,
            "force_login_type": login_type,
        },
    )


@router.post("/init")
def create_init(
    request: Request,
    login_type: Annotated[LoginTypeEnum, Form()],
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
):
    if username.strip() == "":
        return templates.TemplateResponse(
            "init.html",
            {"request": request, "error": "Invalid username"},
            block_name="init_messages",
        )

    try:
        raise_for_invalid_password(session, password, confirm_password)
    except HTTPException as e:
        return templates.TemplateResponse(
            "init.html",
            {"request": request, "error": e.detail},
            block_name="init_messages",
        )

    user = create_user(username, password, GroupEnum.admin, root=True)
    session.add(user)
    auth_config.set_login_type(session, login_type)
    session.commit()

    return Response(status_code=201, headers={"HX-Redirect": "/"})


@router.get("/login")
def redirect_login(request: Request):
    return BaseUrlRedirectResponse("/auth/login?" + urlencode(request.query_params))


@router.post("/debug/populate-sample-data")
def populate_sample_data(
    session: Annotated[Session, Depends(get_session)],
    user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    """Debug endpoint to populate sample data for testing recommendations"""
    from datetime import datetime, timedelta
    import uuid
    from app.internal.models import BookRequest
    
    # Sample book data (these would normally come from Audible API)
    sample_books = [
        {
            "asin": "B07B444HVH", 
            "title": "Atomic Habits",
            "subtitle": "An Easy & Proven Way to Build Good Habits & Break Bad Ones",
            "authors": ["James Clear"],
            "narrators": ["James Clear"],
            "cover_image": "https://m.media-amazon.com/images/I/513Y5o-DYtL.jpg",
            "runtime_length_min": 317,
        },
        {
            "asin": "B0031RS2FU",
            "title": "The 7 Habits of Highly Effective People", 
            "subtitle": "Powerful Lessons in Personal Change",
            "authors": ["Stephen R. Covey"],
            "narrators": ["Stephen R. Covey"],
            "cover_image": "https://m.media-amazon.com/images/I/51Myx7Ka9wL.jpg",
            "runtime_length_min": 463,
        },
        {
            "asin": "B008BUHZPQ",
            "title": "Thinking, Fast and Slow",
            "subtitle": None,
            "authors": ["Daniel Kahneman"],
            "narrators": ["Patrick Egan"],
            "cover_image": "https://m.media-amazon.com/images/I/41shZGS-G%2BL.jpg",
            "runtime_length_min": 1260,
        },
        {
            "asin": "B01LTHUMB6",
            "title": "Sapiens",
            "subtitle": "A Brief History of Humankind",
            "authors": ["Yuval Noah Harari"],
            "narrators": ["Derek Perkins"],
            "cover_image": "https://m.media-amazon.com/images/I/41V%2BihjoxUL.jpg",
            "runtime_length_min": 901,
        }
    ]
    
    created_count = 0
    
    # Add cache entries (books available for discovery)
    for book_data in sample_books:
        existing = session.exec(
            select(BookRequest).where(BookRequest.asin == book_data["asin"])
        ).first()
        
        if not existing:
            book = BookRequest(
                asin=book_data["asin"],
                title=book_data["title"],
                subtitle=book_data["subtitle"],
                authors=book_data["authors"],
                narrators=book_data["narrators"],
                cover_image=book_data["cover_image"],
                release_date=datetime.now() - timedelta(days=100),
                runtime_length_min=book_data["runtime_length_min"],
                user_username=None,  # This makes it a cache entry
            )
            session.add(book)
            created_count += 1
    
    # Add some user requests to make recommendations work
    user_requests = [
        ("B07B444HVH", "testuser1"),  # Atomic Habits requested by testuser1
        ("B07B444HVH", "testuser2"),  # Atomic Habits requested by testuser2 (popular!)
        ("B0031RS2FU", "testuser1"),  # 7 Habits requested by testuser1
        ("B008BUHZPQ", "testuser2"),  # Thinking Fast and Slow requested by testuser2
    ]
    
    for asin, username in user_requests:
        # Find the cache entry
        cache_book = session.exec(
            select(BookRequest).where(
                BookRequest.asin == asin,
                col(BookRequest.user_username).is_(None)
            )
        ).first()
        
        if cache_book:
            # Create user request
            existing_request = session.exec(
                select(BookRequest).where(
                    BookRequest.asin == asin,
                    BookRequest.user_username == username
                )
            ).first()
            
            if not existing_request:
                user_request = BookRequest(
                    asin=cache_book.asin,
                    title=cache_book.title,
                    subtitle=cache_book.subtitle,
                    authors=cache_book.authors,
                    narrators=cache_book.narrators,
                    cover_image=cache_book.cover_image,
                    release_date=cache_book.release_date,
                    runtime_length_min=cache_book.runtime_length_min,
                    user_username=username,
                    updated_at=datetime.now() - timedelta(days=5),
                )
                session.add(user_request)
                created_count += 1
    
    session.commit()
    
    logger.info(f"Created {created_count} sample book entries for testing")
    
    return {"message": f"Populated {created_count} sample entries", "status": "success"}


@router.post("/debug/fetch-popular-books")
async def fetch_popular_books_debug(
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: DetailedUser = Security(ABRAuth(GroupEnum.admin)),
):
    """Debug endpoint to fetch popular books from Audible"""
    from app.util.recommendations import get_popular_books_from_audible
    
    try:
        logger.info("Starting to fetch popular books from Audible...")
        popular_books = await get_popular_books_from_audible(session, client_session, limit=12)
        logger.info(f"Successfully fetched {len(popular_books)} popular books from Audible")
        
        book_titles = [book.title for book in popular_books[:5]]  # First 5 titles for logging
        
        # Also check what's in the database now
        total_cached = session.exec(
            select(func.count()).select_from(BookRequest).where(
                col(BookRequest.user_username).is_(None)
            )
        ).one()
        
        return {
            "message": f"Successfully fetched {len(popular_books)} popular books. Database now has {total_cached} cached books total.", 
            "status": "success",
            "sample_titles": book_titles,
            "total_cached_books": total_cached
        }
    except Exception as e:
        logger.error(f"Failed to fetch popular books: {e}")
        return {"message": f"Failed to fetch popular books: {str(e)}", "status": "error"}
