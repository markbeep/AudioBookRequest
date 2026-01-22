import uuid
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, Request, Form, BackgroundTasks, Security
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
    Library management page. Lists existing books.
    """
    books = session.exec(
        select(Audiobook).where(Audiobook.downloaded == True).order_by(Audiobook.title)
    ).all()
    
    return template_response(
        "library/management.html",
        request,
        user,
        {"books": books}
    )

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
        select(LibraryImportSession).order_by(LibraryImportSession.created_at.desc())
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
    Returns the status of a specific session (polling endpoint).
    """
    import_session = session.get(LibraryImportSession, session_id)
    if not import_session:
        return "Session not found"
    
    items = session.exec(
        select(LibraryImportItem).where(LibraryImportItem.session_id == session_id)
    ).all()
    
    return template_response(
        "library/import.html",
        request,
        user,
        {"session": import_session, "items": items},
        block_name="session_results"
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
    if item:
        item.match_asin = asin
        item.status = ImportItemStatus.matched
        session.add(item)
        session.commit()
        session.refresh(item)
    
    return template_response(
        "library/import_row.html",
        request,
        user,
        {"item": item},
        block_name="item_row"
    )

@router.post("/import/execute/{session_id}")
async def execute_item_import(
    item_id: uuid.UUID,
    import_mode: Annotated[str, Form()],
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
    
    background_tasks.add_task(run_single_importer_task, item_id, import_mode == "move")
    
    return template_response(
        "library/import_row.html",
        request,
        user,
        {"item": item},
        block_name="item_row"
    )

async def run_single_importer_task(item_id: uuid.UUID, move_files: bool):
    """
    Background task to execute a single item import.
    """
    from app.util.db import get_session
    from app.internal.processing.processor import process_completed_download
    from app.internal.models import AudiobookRequest
    
    db_gen = get_session()
    db_session = next(db_gen)
    
    try:
        item = db_session.get(LibraryImportItem, item_id)
        if not item:
            return
            
        # 1. Ensure we have a dummy request
        req = AudiobookRequest(
            asin=item.match_asin,
            user_username="admin",
            processing_status="importing"
        )
        db_session.add(req)
        db_session.commit()
        
        # 2. Call processor
        await process_completed_download(db_session, req, item.source_path, delete_source=move_files)
        
        item.status = ImportItemStatus.imported
        db_session.add(item)
        db_session.commit()
    except Exception as e:
        logger.error("Single import failed", item_id=item_id, error=str(e))
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
    
    use_hardlinks = (import_mode == "move") # or use specialized logic
    background_tasks.add_task(run_importer_task, session_id, import_mode == "move")
    
    return template_response(
        "library/import.html",
        request,
        user,
        {"session": import_session},
        block_name="session_status"
    )

async def run_importer_task(session_id: uuid.UUID, move_files: bool):
    """
    Background task to execute the import.
    """
    from app.util.db import get_session
    from app.internal.processing.processor import process_completed_download
    from app.internal.models import AudiobookRequest
    
    db_gen = get_session()
    db_session = next(db_gen)
    
    try:
        import_session = db_session.get(LibraryImportSession, session_id)
        items = db_session.exec(
            select(LibraryImportItem).where(
                LibraryImportItem.session_id == session_id,
                LibraryImportItem.status == ImportItemStatus.matched
            )
        ).all()
        
        for item in items:
            try:
                # 1. Ensure we have a dummy request for the processor
                # Check if one already exists for this ASIN and 'import' user?
                # Or just create a temporary one.
                req = AudiobookRequest(
                    asin=item.match_asin,
                    user_username="admin", # Or system user
                    processing_status="importing"
                )
                db_session.add(req)
                db_session.commit()
                
                # 2. Call processor
                # We might need to handle 'move' vs 'copy' in processor later.
                # For now, processor does copy/hardlink.
                await process_completed_download(db_session, req, item.source_path, delete_source=move_files)
                
                item.status = ImportItemStatus.imported
                db_session.add(item)
                db_session.commit()
            except Exception as e:
                logger.error("Import failed for item", path=item.source_path, error=str(e))
                item.status = ImportItemStatus.error
                item.error_msg = str(e)
                db_session.add(item)
                db_session.commit()
        
        import_session.status = ImportSessionStatus.completed
        db_session.add(import_session)
        db_session.commit()
        
    finally:
        db_session.close()


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

