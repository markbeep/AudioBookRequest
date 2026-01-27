import os
import json
import uuid
import asyncio
from typing import List, Optional, Tuple
from sqlmodel import Session, select
from aiohttp import ClientSession

from app.internal.models import (
    LibraryImportSession, 
    LibraryImportItem, 
    ImportItemStatus, 
    ImportSessionStatus,
    Audiobook
)
from app.internal.library.scanner import LibraryScanner
from app.internal.media_management.config import media_management_config
from app.util.log import logger
from app.util.db import get_session

class LibraryReconciler(LibraryScanner):
    """
    Specialized scanner that looks at the INTERNAL library and finds books 
    not currently tracked in the database.
    """
    
    async def reconcile(self, client_session: ClientSession):
        root = ""
        with next(get_session()) as session:
            root = media_management_config.get_library_path(session)
            if not root or not os.path.exists(root):
                logger.error("Reconciler: Library path not found or invalid", path=root)
                return

        logger.info("Reconciler: Scanning library for untracked books", path=root)
        
        # 1. Identify all book units in the library
        # We reuse the scanner's unit detection but we'll be more strict
        book_units = self._find_book_units(root)
        
        semaphore = asyncio.Semaphore(10)
        
        async def process_unit(unit_data: Tuple[str, Optional[str], str, Optional[str]]):
            path, author_guess, title_guess, language_guess = unit_data
            
            # Check for metadata.json first
            asin = None
            if os.path.isdir(path):
                meta_path = os.path.join(path, "metadata.json")
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            asin = data.get("asin")
                    except: pass
            
            async with semaphore:
                with next(get_session()) as session:
                    # Check if this ASIN is already in DB and marked downloaded
                    if asin:
                        existing = session.get(Audiobook, asin)
                        if existing and existing.downloaded:
                            return # Already tracked, skip
                    
                    # If no ASIN, check by path/title (heuristic)
                    # This is slower but handles legacy folders
                    if not asin:
                        # Find by title match
                        existing_by_title = session.exec(
                            select(Audiobook).where(Audiobook.title == title_guess, Audiobook.downloaded == True)
                        ).first()
                        if existing_by_title:
                            return # Likely already tracked

                    # If we got here, it's physically there but not in DB
                    # Create an import item for it
                    item = LibraryImportItem(
                        session_id=self.import_session_id,
                        source_path=path,
                        detected_author=author_guess,
                        detected_title=title_guess,
                        status=ImportItemStatus.pending,
                        match_asin=asin
                    )
                    session.add(item)
                    session.commit()
                    session.refresh(item)
                    
                    if asin:
                        item.status = ImportItemStatus.matched
                        book = session.get(Audiobook, asin)
                        title_candidates, author_candidates = (
                            self._build_match_candidates(item)
                        )
                        if book and self._is_exact_title_author_match(
                            title_candidates, author_candidates, book
                        ):
                            item.match_score = 1.0
                        else:
                            item.match_score = 0.95
                        session.add(item)
                        session.commit()
                    else:
                        # Auto-match it
                        await self._auto_match(item, session, client_session, language_guess)

        tasks = [process_unit(u) for u in book_units]
        if tasks:
            await asyncio.gather(*tasks)

        # Clean up any items still stuck in pending after scan completes
        with next(get_session()) as session:
            pending_items = session.exec(
                select(LibraryImportItem).where(
                    LibraryImportItem.session_id == self.import_session_id,
                    LibraryImportItem.status == ImportItemStatus.pending,
                )
            ).all()
            if pending_items:
                for item in pending_items:
                    if item.match_asin:
                        item.status = ImportItemStatus.matched
                        if not item.match_score:
                            book = session.get(Audiobook, item.match_asin)
                            title_candidates, author_candidates = (
                                self._build_match_candidates(item)
                            )
                            if book and self._is_exact_title_author_match(
                                title_candidates, author_candidates, book
                            ):
                                item.match_score = 1.0
                            else:
                                item.match_score = 0.95
                    else:
                        item.status = ImportItemStatus.missing
                session.add_all(pending_items)
                session.commit()

        # Update session status
        with next(get_session()) as session:
            import_session = session.get(LibraryImportSession, self.import_session_id)
            if import_session:
                import_session.status = ImportSessionStatus.review_ready
                session.add(import_session)
                session.commit()
