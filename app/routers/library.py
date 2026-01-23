import uuid
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, Request, Form, BackgroundTasks, Security
from fastapi.responses import HTMLResponse
from sqlmodel import Session, select
from app.util.db import get_session
from app.util.templates import template_response
from app.internal.auth.authentication import ABRAuth, DetailedUser, GroupEnum
from app.internal.models import LibraryImportSession, LibraryImportItem, ImportSessionStatus, ImportItemStatus, Audiobook
from app.internal.library.scanner import LibraryScanner
from app.util.connection import get_connection
from aiohttp import ClientSession
from app.util.log import logger

router = APIRouter(prefix="/library", tags=["Library"])

@router.get("")
async def library_management(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    """
    Library management page. Lists existing books and checks for untracked files.
    """
    books = session.exec(
        select(Audiobook).where(Audiobook.downloaded == True).order_by(Audiobook.title)
    ).all()
    
    # Check for latest reconciliation session
    recon_session = session.exec(
        select(LibraryImportSession).where(LibraryImportSession.root_path == "__INTERNAL_LIBRARY__").order_by(LibraryImportSession.created_at.desc())
    ).first()
    
    return template_response(
        "library/management.html",
        request,
        user,
        {"books": books, "recon_session": recon_session}
    )

@router.post("/reconcile/start")
async def start_reconciliation(
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    """
    Starts a library reconciliation scan.
    """
    try:
        old_sessions = session.exec(
            select(LibraryImportSession).where(LibraryImportSession.root_path == "__INTERNAL_LIBRARY__")
        ).all()
        for s in old_sessions:
            session.delete(s)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.warning("Failed to clean up old reconciliation sessions", error=str(e))

    new_session = LibraryImportSession(root_path="__INTERNAL_LIBRARY__", status=ImportSessionStatus.scanning)
    session.add(new_session)
    session.commit()
    session.refresh(new_session)
    
    background_tasks.add_task(run_reconciler_task, new_session.id)
    
    return HTMLResponse("""<div hx-get="/library/reconcile/status" hx-trigger="load, every 2s" hx-swap="outerHTML">
                <div class="alert alert-info py-2 rounded-2xl shadow-sm border-0 animate-pulse">
                    <span class="loading loading-spinner loading-xs"></span>
                    <span class="font-black uppercase text-[10px] tracking-wider">Scanning Library...</span>
                </div>
              </div>""")

@router.get("/reconcile/status")
async def get_reconcile_status(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    """
    Returns the current status of library reconciliation.
    """
    recon_session = session.exec(
        select(LibraryImportSession).where(LibraryImportSession.root_path == "__INTERNAL_LIBRARY__").order_by(LibraryImportSession.created_at.desc())
    ).first()
    
    if not recon_session:
        return HTMLResponse("")
        
    if recon_session.status == ImportSessionStatus.scanning:
        return HTMLResponse("""<div hx-get="/library/reconcile/status" hx-trigger="load, every 2s" hx-swap="outerHTML">
                    <div class="alert alert-info py-2 rounded-2xl shadow-sm border-0 animate-pulse">
                        <span class="loading loading-spinner loading-xs"></span>
                        <span class="font-black uppercase text-[10px] tracking-wider">Scanning Library...</span>
                    </div>
                  </div>""")
    
    items = session.exec(
        select(LibraryImportItem).where(LibraryImportItem.session_id == recon_session.id)
    ).all()
    
    untracked_items = [i for i in items if i.status not in [ImportItemStatus.imported, ImportItemStatus.ignored]]
    
    if untracked_items:
        return HTMLResponse(f"""
        <div class="alert alert-warning py-2 rounded-2xl shadow-lg border-0 flex justify-between items-center animate-in slide-in-from-top-4 duration-500">
            <div class="flex items-center gap-3">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2.5" stroke="currentColor" class="w-5 h-5 text-warning">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
                </svg>
                <span class="font-black uppercase text-[10px] tracking-wider">{len(untracked_items)} Untracked books in your library</span>
            </div>
            <a href="/library/import/session/{recon_session.id}" class="btn btn-xs btn-ghost bg-base-100/50 hover:bg-base-100 rounded-lg font-black uppercase text-[9px]">Review & Add</a>
        </div>
        """)
    
    if recon_session.status == ImportSessionStatus.review_ready:
        return HTMLResponse("""
        <div class="alert alert-success py-2 rounded-2xl shadow-sm border-0 flex justify-between items-center animate-in fade-in duration-500">
            <div class="flex items-center gap-3">
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="3" stroke="currentColor" class="w-5 h-5 text-success">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                </svg>
                <span class="font-black uppercase text-[10px] tracking-wider">Library is fully synced</span>
            </div>
            <button class="btn btn-xs btn-ghost rounded-lg font-black uppercase text-[9px]" onclick="this.parentElement.remove()">Dismiss</button>
        </div>
        """)
        
    return HTMLResponse("")

async def run_reconciler_task(session_id: uuid.UUID):
    """
    Background task wrapper for the reconciler.
    """
    import aiohttp
    from app.internal.library.reconciler import LibraryReconciler
    
    try:
        async with aiohttp.ClientSession() as client_session:
            reconciler = LibraryReconciler(session_id)
            await reconciler.reconcile(client_session)
    except Exception as e:
        logger.error("Reconciler task failed", error=str(e))
        from app.util.db import get_session
        with next(get_session()) as session:
            import_session = session.get(LibraryImportSession, session_id)
            if import_session:
                import_session.status = ImportSessionStatus.failed
                session.add(import_session)
                session.commit()

@router.get("/import")
async def import_page(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    """
    Main import page. Shows current active sessions or a form to start a new one.
    """
    active_sessions = session.exec(
        select(LibraryImportSession).where(LibraryImportSession.root_path != "__INTERNAL_LIBRARY__").order_by(LibraryImportSession.created_at.desc())
    ).all()
    
    return template_response(
        "library/import.html",
        request,
        user,
        {"sessions": active_sessions}
    )

@router.post("/import/scan")
async def start_scan(
    request: Request,
    background_tasks: BackgroundTasks,
    path: Annotated[str, Form()],
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    """
    Starts a new scan session.
    """
    new_session = LibraryImportSession(root_path=path, status=ImportSessionStatus.scanning)
    session.add(new_session)
    session.commit()
    session.refresh(new_session)
    
    background_tasks.add_task(run_scanner_task, new_session.id)
    
    return template_response(
        "library/import.html",
        request,
        user,
        {"session": new_session},
        block_name="session_status"
    )

@router.get("/import/session/{session_id}")
async def get_session_status(
    session_id: uuid.UUID,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    """
    Returns the status of a specific session (polling endpoint or full page).
    """
    import_session = session.get(LibraryImportSession, session_id)
    if not import_session:
        return "Session not found"

    items = session.exec(
        select(LibraryImportItem).where(LibraryImportItem.session_id == session_id)
    ).all()

    # Pre-fetch books to avoid N+1 DB calls in template filters
    asins = {i.match_asin for i in items if i.match_asin}
    books_map = {}
    if asins:
        books = session.exec(select(Audiobook).where(Audiobook.asin.in_(list(asins)))).all()
        books_map = {b.asin: b for b in books}

    is_htmx = request.headers.get("HX-Request") == "true"
    return template_response(
        "library/import.html",
        request,
        user,
        {"session": import_session, "items": items, "books_map": books_map},
        block_name="session_status" if is_htmx else None
    )

@router.get("/import/item/status/{item_id}")
async def get_item_status(
    item_id: uuid.UUID,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    """
    Returns the status of a single item (row polling).
    """
    item = session.get(LibraryImportItem, item_id)
    if not item: return ""

    books_map = {}
    if item.match_asin:
        book = session.get(Audiobook, item.match_asin)
        if book: books_map = {book.asin: book}

    return template_response(
        "library/import_row.html",
        request,
        user,
        {"item": item, "books_map": books_map},
        block_name="item_row"
    )

@router.get("/import/fix-match/{item_id}")
async def fix_match_modal(
    item_id: uuid.UUID,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    """
    Returns the modal for fixing a match.
    """
    item = session.get(LibraryImportItem, item_id)
    return template_response(
        "library/import_modals.html",
        request,
        user,
        {"item": item},
        block_name="fix_match_modal"
    )

@router.get("/import/search")
async def search_for_match(
    q: str,
    item_id: uuid.UUID,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    client_session: Annotated[ClientSession, Depends(get_connection)],
    user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    """
    Searches for a book to match manually.
    """
    from app.internal.book_search import list_audible_books
    books = await list_audible_books(session, client_session, q, num_results=5) 
    # Wrap in dict for template compatibility: result.book
    results = [{"book": b} for b in books]
    return template_response(
        "library/import_modals.html",
        request,
        user,
        {"results": results, "item_id": item_id},
        block_name="search_results"
    )

@router.post("/import/match/{item_id}/{asin}")
async def update_match(
    item_id: uuid.UUID,
    asin: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    """
    Updates an item with a manually selected ASIN.
    """
    item = session.get(LibraryImportItem, item_id)
    books_map = {}
    if item:
        item.match_asin = asin
        item.match_score = 1.0 # 100% score for manual match
        item.status = ImportItemStatus.matched
        session.add(item)
        session.commit()
        session.refresh(item)

        book = session.get(Audiobook, asin)
        if book: books_map = {book.asin: book}

    return template_response(
        "library/import_row.html",
        request,
        user,
        {"item": item, "books_map": books_map},
        block_name="item_row"
    )

@router.post("/import/item/execute/{item_id}")
async def execute_item_import(
    item_id: uuid.UUID,
    import_mode: Annotated[str, Form()],
    request: Request,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    """
    Starts the import process for a single item.
    """
    item = session.get(LibraryImportItem, item_id)
    if not item or item.status != ImportItemStatus.matched:
        return "Item not found or not matched"

    item.status = ImportItemStatus.pending # Use pending as 'queued'
    session.add(item)
    session.commit()

    background_tasks.add_task(run_single_importer_task, item_id, import_mode == "move", user.username)

    return template_response(
        "library/import_row.html",
        request,
        user,
        {"item": item},
        block_name="item_row"
    )

async def run_single_importer_task(item_id: uuid.UUID, move_files: bool, username: str):
    """
    Background task to execute a single item import.
    """
    from app.util.db import get_session
    from app.internal.processing.processor import process_completed_download    
    from app.internal.models import AudiobookRequest, Audiobook, LibraryImportSession

    db_gen = get_session()
    db_session = next(db_gen)

    try:
        item = db_session.get(LibraryImportItem, item_id)
        if not item or not item.match_asin:
            return

        import_session = db_session.get(LibraryImportSession, item.session_id)  
        is_reconciliation = import_session and import_session.root_path == "__INTERNAL_LIBRARY__"

        # Ensure book exists in DB
        book = db_session.get(Audiobook, item.match_asin)
        if not book:
            from app.internal.book_search import get_book_by_asin
            import aiohttp
            async with aiohttp.ClientSession() as client_session:
                await get_book_by_asin(client_session, item.match_asin)
            book = db_session.get(Audiobook, item.match_asin)

        # Guard: Check if already in library (and not in reconciliation mode)
        if not is_reconciliation and book and book.downloaded:
            item.status = ImportItemStatus.imported
            db_session.add(item)
            db_session.commit()
            return

        # 1. Ensure we have a dummy request
        req = db_session.exec(
            select(AudiobookRequest).where(
                AudiobookRequest.asin == item.match_asin,
                AudiobookRequest.user_username == username
            )
        ).first()

        if not req:
            req = AudiobookRequest(
                asin=item.match_asin,
                user_username=username,
                processing_status="importing"
            )
            db_session.add(req)
            db_session.commit()
            db_session.refresh(req)

        # 2. Call processor
        # If reconciliation, we force organization (rename/move) to standardized paths
        await process_completed_download(db_session, req, item.source_path, delete_source=True if is_reconciliation else move_files)

        item.status = ImportItemStatus.imported
        db_session.add(item)
        db_session.commit()
    except Exception as e:
        db_session.rollback()
        logger.error("Single import failed", item_id=item_id, error=str(e))     
        item = db_session.get(LibraryImportItem, item_id)
        if item:
            item.status = ImportItemStatus.error
            item.error_msg = str(e)
            db_session.add(item)
            db_session.commit()
    finally:
        db_session.close()

@router.post("/import/execute/{session_id}")
async def execute_import(
    session_id: uuid.UUID,
    import_mode: Annotated[str, Form()],
    request: Request,
    background_tasks: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    user: Annotated[DetailedUser, Security(ABRAuth(GroupEnum.admin))],
):
    """
    Starts the actual file moving/copying process.
    """
    import_session = session.get(LibraryImportSession, session_id)
    if not import_session:
        return "Session not found"

    import_session.status = ImportSessionStatus.importing
    session.add(import_session)
    session.commit()

    background_tasks.add_task(run_importer_task, session_id, import_mode == "move", user.username)

    # Pre-fetch for the response
    items = session.exec(select(LibraryImportItem).where(LibraryImportItem.session_id == session_id)).all()
    asins = {i.match_asin for i in items if i.match_asin}
    books_map = {b.asin: b for b in session.exec(select(Audiobook).where(Audiobook.asin.in_(list(asins)))).all()} if asins else {}

    return template_response(
        "library/import.html",
        request,
        user,
        {"session": import_session, "items": items, "books_map": books_map},    
        block_name="session_status"
    )

async def run_importer_task(session_id: uuid.UUID, move_files: bool, username: str):
    """
    Background task to execute the import in parallel (5 at a time).
    """
    from app.util.db import get_session
    from app.internal.processing.processor import process_completed_download    
    from app.internal.models import AudiobookRequest, Audiobook, LibraryImportSession
    import asyncio

    # Get the list of items to import
    with next(get_session()) as db_session:
        import_session_obj = db_session.get(LibraryImportSession, session_id)   
        is_reconciliation = import_session_obj and import_session_obj.root_path == "__INTERNAL_LIBRARY__"

        items = db_session.exec(
            select(LibraryImportItem).where(
                LibraryImportItem.session_id == session_id,
                LibraryImportItem.status == ImportItemStatus.matched
            )
        ).all()
        item_ids = [item.id for item in items]

    semaphore = asyncio.Semaphore(5)

    async def import_item_task(item_id: uuid.UUID):
        async with semaphore:
            with next(get_session()) as db_session:
                try:
                    item = db_session.get(LibraryImportItem, item_id)
                    if not item or not item.match_asin:
                        return

                    item.status = ImportItemStatus.pending
                    db_session.add(item)
                    db_session.commit()

                    book = db_session.get(Audiobook, item.match_asin)
                    if not book:
                        from app.internal.book_search import get_book_by_asin   
                        import aiohttp
                        async with aiohttp.ClientSession() as client_session:   
                            await get_book_by_asin(client_session, item.match_asin)
                        book = db_session.get(Audiobook, item.match_asin)       

                    if not is_reconciliation and book and book.downloaded:
                        item.status = ImportItemStatus.imported
                        db_session.add(item)
                        db_session.commit()
                        return

                    req = db_session.exec(
                        select(AudiobookRequest).where(
                            AudiobookRequest.asin == item.match_asin,       
                            AudiobookRequest.user_username == username      
                        )
                    ).first()

                    if not req:
                        req = AudiobookRequest(
                            asin=item.match_asin,
                            user_username=username,
                            processing_status="importing"
                        )
                        db_session.add(req)
                        db_session.commit()
                        db_session.refresh(req)

                    # If reconciliation, force organization into standardized paths
                    await process_completed_download(db_session, req, item.source_path, delete_source=True if is_reconciliation else move_files)

                    item.status = ImportItemStatus.imported
                    db_session.add(item)
                    db_session.commit()
                except Exception as e:
                    db_session.rollback()
                    logger.error("Parallel import failed for item", item_id=item_id, error=str(e))
                    item = db_session.get(LibraryImportItem, item_id)
                    if item:
                        item.status = ImportItemStatus.error
                        item.error_msg = str(e)
                        db_session.add(item)
                        db_session.commit()

    # Launch all tasks
    tasks = [import_item_task(iid) for iid in item_ids]
    if tasks:
        await asyncio.gather(*tasks)

    with next(get_session()) as db_session:
        import_session = db_session.get(LibraryImportSession, session_id)       
        if import_session:
            import_session.status = ImportSessionStatus.completed
            db_session.add(import_session)
            db_session.commit()
async def run_scanner_task(session_id: uuid.UUID):
    """
    Background task wrapper for the scanner.
    """
    import aiohttp
    from app.util.log import logger
    
    try:
        async with aiohttp.ClientSession() as client_session:
            scanner = LibraryScanner(session_id)
            await scanner.scan(client_session)
    except Exception as e:
        logger.error("Scanner task failed", error=str(e))
        from app.util.db import get_session
        with next(get_session()) as session:
            import_session = session.get(LibraryImportSession, session_id)
            if import_session:
                import_session.status = ImportSessionStatus.failed
                session.add(import_session)
                session.commit()
