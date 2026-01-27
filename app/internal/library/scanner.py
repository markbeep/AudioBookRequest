import os
import re
import uuid
import asyncio
import json
from typing import List, Optional, Tuple
from sqlmodel import Session, select
from aiohttp import ClientSession
from rapidfuzz import fuzz

from app.internal.models import (
    LibraryImportSession,
    LibraryImportItem,
    ImportItemStatus,
    ImportSessionStatus,
    Audiobook,
)
from app.internal.book_search import list_audible_books
from app.util.log import logger
from app.util.db import get_session
from app.util.sort import natural_sort

# Common single-file audiobook extensions
SINGLE_FILE_EXTENSIONS = {".m4b", ".m4a"}
AUDIO_EXTENSIONS = {
    ".m4b",
    ".mp3",
    ".m4a",
    ".flac",
    ".wav",
    ".ogg",
    ".opus",
    ".aac",
    ".wma",
}


class LibraryScanner:
    def __init__(self, import_session_id: uuid.UUID):
        self.import_session_id = import_session_id

    async def scan(self, client_session: ClientSession):
        """
        Deep scans the root path and populates ImportItems in parallel.
        """
        root = ""
        with next(get_session()) as session:
            import_session = session.get(LibraryImportSession, self.import_session_id)
            if not import_session:
                logger.error(
                    "Scanner: Session ghosted", session_id=self.import_session_id
                )
                return
            root = import_session.root_path

        logger.info("Scanner: Diving into the deep end", path=root)

        book_units = self._find_book_units(root)
        logger.info("Scanner: Found units", count=len(book_units))

        semaphore = asyncio.Semaphore(5)

        async def process_unit(
            unit_data: Tuple[str, Optional[str], str, Optional[str]],
        ):
            path, author_guess, title_guess, language_guess = unit_data
            async with semaphore:
                with next(get_session()) as session:
                    try:
                        # Check for duplicates in current session
                        existing = session.exec(
                            select(LibraryImportItem).where(
                                LibraryImportItem.session_id == self.import_session_id,
                                LibraryImportItem.source_path == path,
                            )
                        ).first()
                        if existing:
                            return

                        item = LibraryImportItem(
                            session_id=self.import_session_id,
                            source_path=path,
                            detected_author=author_guess,
                            detected_title=title_guess,
                            status=ImportItemStatus.pending,
                        )
                        session.add(item)
                        session.commit()
                        session.refresh(item)

                        await self._auto_match(
                            item, session, client_session, language_guess
                        )
                    except Exception as e:
                        logger.error(
                            "Scanner: Unit tripped up", path=path, error=str(e)
                        )
                        session.rollback()

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

        # Update final status
        with next(get_session()) as session:
            import_session = session.get(LibraryImportSession, self.import_session_id)
            if import_session:
                import_session.status = ImportSessionStatus.review_ready
                session.add(import_session)
                session.commit()

        logger.info(
            "Scanner: Deep scan done and dusted", session_id=self.import_session_id
        )

    def _looks_like_garbage(self, name: str) -> bool:
        """Suss out if a filename is 8.3 style gibberish (e.g. MI20D0~1.MP3)"""
        if re.match(r"(?i)^MI[0-9A-Z~]{5,}", name):
            return True
        if "~" in name and len(name) < 13:
            return True
        return False

    def _find_book_units(
        self, root: str
    ) -> List[Tuple[str, Optional[str], str, Optional[str]]]:
        """
        Identify what constitutes a 'book' in the filesystem.
        """
        units = []
        for dirpath, dirnames, filenames in os.walk(root):
            # 0. Detect "Folder of Parts" (CD1, Disc 2, etc.)
            if dirnames:
                part_dir_markers = r"(?i)^(cd|part|disc|volume|pt|level|buch)\.?\s*\d+$"
                matches_part_dir = [
                    d for d in dirnames if re.search(part_dir_markers, d)
                ]
                if matches_part_dir and len(matches_part_dir) >= len(dirnames) * 0.5:
                    if not any(u[0] == dirpath for u in units):
                        author, title, lang = self._guess_from_path(
                            dirpath, root, is_file=False
                        )
                        units.append((dirpath, author, title, lang))
                    dirnames[:] = []
                    continue

            audio_files = [
                f
                for f in filenames
                if os.path.splitext(f)[1].lower() in AUDIO_EXTENSIONS
            ]
            if not audio_files:
                continue

            natural_sort(audio_files)

            # --- EXTRACT FULL MASTER BOOKS (M4B, M4A) ---
            # Files that aren't marked as "Chapter X" or "Part Y"
            markers = r"(?i)\b(part|pt|disc|cd|volume|vol|v|chp|chapter|level|buch)\.?\s*\d+\b|[\s\-\.]\d+$"
            master_books_found = []

            candidates = [
                f
                for f in audio_files
                if os.path.splitext(f)[1].lower() in SINGLE_FILE_EXTENSIONS
            ]
            for f in candidates:
                if not re.search(markers, os.path.splitext(f)[0]):
                    fpath = os.path.join(dirpath, f)
                    author, title, lang = self._guess_from_path(
                        fpath, root, is_file=True
                    )
                    units.append((fpath, author, title, lang))
                    master_books_found.append(f)

            remaining_audio = [f for f in audio_files if f not in master_books_found]
            if not remaining_audio:
                continue

            # --- GROUP REMAINING BY PREFIX ---
            groups = {}
            for f in remaining_audio:
                if self._looks_like_garbage(f):
                    key = "garbage_bin"
                else:
                    clean = self._clean_string(f)
                    # Strip everything but letters for the key to ensure grouping works regardless of digits/symbols
                    key = re.sub(r"[^a-z]", "", clean.lower())[:12]
                    if not key:
                        key = "misc_pile"

                if key not in groups:
                    groups[key] = []
                groups[key].append(f)

            # Analyze each group
            for key, group_files in groups.items():
                if not group_files:
                    continue

                is_collection = False
                matches_marker = [
                    f for f in group_files if re.search(markers, os.path.splitext(f)[0])
                ]

                if len(group_files) > 1:
                    # If they share garbage prefix or common markers, they are a collection
                    if (
                        key == "garbage_bin"
                        or len(matches_marker) / len(group_files) > 0.4
                    ):
                        is_collection = True
                    else:
                        if fuzz.ratio(group_files[0], group_files[-1]) > 60:
                            is_collection = True

                # De-duplication logic: Skip MP3 collections if a master version is already there
                if master_books_found and is_collection:
                    prefix = key[:8]
                    redundant = False
                    for master in master_books_found:
                        m_key = re.sub(
                            r"[^a-z]", "", self._clean_string(master).lower()
                        )[:8]
                        if prefix == m_key:
                            redundant = True
                            break
                    if redundant:
                        logger.debug(
                            "Scanner: Tossed redundant loose files", prefix=key
                        )
                        continue

                # If this group is the ONLY thing in the folder, claim the FOLDER.
                if len(groups) == 1 and not master_books_found and is_collection:
                    if not any(u[0] == dirpath for u in units):
                        author, title, lang = self._guess_from_path(
                            dirpath, root, is_file=False
                        )
                        units.append((dirpath, author, title, lang))
                    dirnames[:] = []
                    break

                if is_collection:
                    rep_f = group_files[0]
                    rep_path = os.path.join(dirpath, rep_f)
                    joined_path = "|".join(
                        [os.path.join(dirpath, f) for f in group_files]
                    )
                    author, title, lang = self._guess_from_path(
                        rep_path, root, is_file=True
                    )
                    units.append((joined_path, author, title, lang))
                else:
                    for f in group_files:
                        fpath = os.path.join(dirpath, f)
                        author, title, lang = self._guess_from_path(
                            fpath, root, is_file=True
                        )
                        units.append((fpath, author, title, lang))

        return units

    def _guess_from_path(
        self, path: str, root: str, is_file: bool
    ) -> Tuple[Optional[str], str, Optional[str]]:
        # Take the first file if it's a bundle
        actual_path = path.split("|")[0]
        rel = os.path.relpath(actual_path, root)
        parts = rel.split(os.sep)
        name = os.path.basename(actual_path)
        if is_file:
            name = os.path.splitext(name)[0]

        lang = self._detect_language(name)
        if not lang and len(parts) >= 2:
            lang = self._detect_language(parts[-2])

        author, title = self._parse_name(name)
        clean_t = self._clean_string(title)

        # Suss out junk titles
        if is_file and (
            self._looks_like_garbage(name)
            or not clean_t
            or clean_t.isdigit()
            or len(clean_t) < 3
        ):
            title = ""

        if (not author or not title) and len(parts) >= 2:
            # Check the neighborhood (folders above)
            p_author, p_title = self._parse_name(parts[-2])

            if is_file:
                # [Root, AuthorFolder, TitleFolder, File]
                if len(parts) >= 3:
                    # Look at grandparent for author clues
                    gp_author, _ = self._parse_name(parts[-3])
                    if gp_author:
                        author = gp_author
                    elif not author:
                        author = parts[-3]

                    if not title:
                        if p_title:
                            title = p_title
                        else:
                            title = parts[-2]
                else:
                    # [Root, AuthorTitleFolder, File]
                    if p_author and not author:
                        author = p_author
                    if not title:
                        if p_title:
                            title = p_title
                        else:
                            title = parts[-2]
            else:
                # Folder-based book. Parent might be the author.
                if not author:
                    if p_author:
                        author = p_author
                    else:
                        author = parts[-2]

        return author, title, lang

    def _detect_language(self, text: str) -> Optional[str]:
        if not text:
            return None
        if re.search(r"(?i)\bbuch\b", text):
            return "de"
        # Sniff out (GER), [French], etc.
        match = re.search(
            r"(?i)[\[\(_\s](ger|german|de|fre|french|fr|ita|italian|it|spa|spanish|es|jpn|japanese|jp)[\]\)_\s]",
            text,
        )
        if match:
            found = match.group(1).lower()
            if found in ["ger", "german", "de"]:
                return "de"
            if found in ["fre", "french", "fr"]:
                return "fr"
            if found in ["ita", "italian", "it"]:
                return "it"
            if found in ["spa", "spanish", "es"]:
                return "es"
            if found in ["jpn", "japanese", "jp"]:
                return "jp"
        return None

    def _clean_string(self, name: str) -> str:
        if not name:
            return ""
        # Cut off extensions
        name = re.sub(
            r"\.(m4b|mp3|m4a|flac|wav|ogg|opus|aac|wma)$", "", name, flags=re.IGNORECASE
        )

        # Scrub typical technical noise
        name = name.replace("_", " ").replace(".", " ")
        name = re.sub(r"(?i)\bAD\d+\b", "", name)  # No AD05
        name = re.sub(r"(?i)@\d+", "", name)  # No bitrates
        name = re.sub(r"\(([^)]+)\)", r" \1 ", name)
        name = re.sub(r"\[([^\]]+)\]", r" \1 ", name)
        name = re.sub(r"\{[^\}]+\}", "", name)  # Toss narrators in curly braces

        # Nuke standalone noise words
        noise = r"(?i)\b(unabridged|abridged|audiobook|hq|kbps|aac|mp3|m4b|m4a|flac|dramatisation|dramatized|full\s*cast|bbc|read by|narrated by|ger|french|german|buch|level|U)\b"
        name = re.sub(noise, "", name)

        # Scrub part/chapter markers
        name = re.sub(
            r"(?i)\b(chp|chapter|part|pt|disc|cd|volume|vol|v|track|level|buch|book)\s*\d+\b",
            "",
            name,
        )
        # Handle c4p6, c01, p01 style markers
        name = re.sub(r"(?i)\bc\d+p\d+\b", "", name)
        name = re.sub(r"(?i)\b[cp]\d+\b", "", name)

        # Trim leading/trailing digits and dashes
        name = re.sub(r"^\s*\d+[\s\-]+", "", name)
        name = re.sub(r"[\s\-]+\d+\s*$", "", name)

        # Polish whitespace
        name = re.sub(r"\s+", " ", name).strip()
        return name

    def _normalize_text(self, text: str) -> str:
        if not text:
            return ""
        text = self._clean_string(text).lower()
        text = text.replace("&", " and ")
        text = re.sub(r"[^a-z0-9]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _compact_text(self, text: str) -> str:
        if not text:
            return ""
        text = self._normalize_text(text)
        return re.sub(r"[^a-z0-9]", "", text)

    def _score_text_pair(self, left: str, right: str) -> float:
        if not left or not right:
            return 0.0
        left_norm = self._normalize_text(left)
        right_norm = self._normalize_text(right)
        if not left_norm or not right_norm:
            return 0.0

        score = max(
            fuzz.ratio(left_norm, right_norm),
            fuzz.token_set_ratio(left_norm, right_norm),
            fuzz.partial_ratio(left_norm, right_norm),
            fuzz.WRatio(left_norm, right_norm),
        )

        left_compact = self._compact_text(left)
        right_compact = self._compact_text(right)
        if left_compact and right_compact:
            score = max(
                score,
                fuzz.ratio(left_compact, right_compact),
                fuzz.partial_ratio(left_compact, right_compact),
            )

        return score

    def _dedupe_candidates(self, values: list[str]) -> list[str]:
        seen = set()
        result = []
        for value in values:
            if not value:
                continue
            value = value.strip()
            if len(value) < 2:
                continue
            key = self._normalize_text(value) or value.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(value)
        return result

    def _parse_name(self, name: str) -> Tuple[Optional[str], str]:
        if not name:
            return None, ""
        clean_name = self._clean_string(name)
        if " - " in clean_name:
            parts = [p.strip() for p in clean_name.split(" - ") if p.strip()]
            if len(parts) >= 3:
                last = parts[-1].strip()
                if re.match(r"^\d+$", last) or len(last) < 4 or "kbps" in last.lower():
                    parts.pop()
            if len(parts) >= 2:
                return parts[0].strip(), parts[1].strip()
            elif len(parts) == 1:
                return None, parts[0].strip()
        return None, clean_name

    def _extract_asin(self, text: str) -> Optional[str]:
        # ASIN hunt
        match = re.search(
            r"(?:^|[^A-Z0-9])(B0[A-Z0-9]{8})(?:$|[^A-Z0-9])", text, re.IGNORECASE
        )
        return match.group(1).upper() if match else None

    def _build_match_candidates(
        self, item: LibraryImportItem
    ) -> Tuple[list[str], list[str]]:
        folder_clean = self._clean_string(
            os.path.basename(os.path.dirname(item.source_path.split("|")[0]))
        )
        file_clean = self._clean_string(
            os.path.basename(item.source_path.split("|")[0])
        )

        extra_title, extra_author = None, None
        if item.detected_title and " by " in item.detected_title.lower():
            parts = re.split(r"(?i)\s+by\s+", item.detected_title, maxsplit=1)
            if len(parts) == 2:
                extra_title, extra_author = parts[0].strip(), parts[1].strip()

        title_candidates = self._dedupe_candidates(
            [
                item.detected_title or "",
                extra_title or "",
                folder_clean or "",
                file_clean or "",
            ]
        )
        author_candidates = self._dedupe_candidates(
            [
                item.detected_author or "",
                extra_author or "",
            ]
        )

        return title_candidates, author_candidates

    def _expand_author_candidates(self, author_candidates: list[str]) -> list[str]:
        expanded: list[str] = []
        for author in author_candidates:
            if not author:
                continue
            parts = re.split(r"\s*(?:,|&| and )\s*", author, flags=re.IGNORECASE)
            expanded.extend([p.strip() for p in parts if p.strip()])
        return self._dedupe_candidates(expanded)

    def _is_exact_title_author_match(
        self,
        title_candidates: list[str],
        author_candidates: list[str],
        book: Audiobook,
    ) -> bool:
        if not book or not book.title or not book.authors:
            return False

        normalized_titles = set()
        normalized_titles.add(self._normalize_text(book.title))
        subtitle = getattr(book, "subtitle", None)
        if subtitle:
            normalized_titles.add(self._normalize_text(f"{book.title} {subtitle}"))

        title_match = False
        for title in title_candidates:
            if not title:
                continue
            if self._normalize_text(title) in normalized_titles:
                title_match = True
                break
        if not title_match:
            return False

        normalized_authors = {
            self._normalize_text(author)
            for author in (book.authors or [])
            if author
        }
        if not normalized_authors:
            return False

        for author in self._expand_author_candidates(author_candidates):
            if self._normalize_text(author) in normalized_authors:
                return True
        return False

    async def _auto_match(
        self,
        item: LibraryImportItem,
        session: Session,
        client_session: ClientSession,
        language: Optional[str] = None,
    ):
        title_candidates, author_candidates = self._build_match_candidates(item)

        # 1. Fast path: Direct ASIN hit
        path_asin = self._extract_asin(item.source_path)
        if path_asin:
            from app.internal.book_search import get_book_by_asin

            try:
                book = await get_book_by_asin(client_session, path_asin)
                if book:
                    exact_match = self._is_exact_title_author_match(
                        title_candidates, author_candidates, book
                    )
                    match_score = 1.0 if exact_match else 0.98
                    item.match_asin, item.match_score, item.status = (
                        book.asin,
                        match_score,
                        ImportItemStatus.matched,
                    )
                    session.add(item)
                    session.commit()
                    return
            except Exception as e:
                logger.warning("ASIN hunt failed", asin=path_asin, error=str(e))

        # 2. Scour search queries
        search_queries = []
        search_queries.extend(title_candidates)
        if author_candidates and title_candidates:
            for author in author_candidates:
                for title in title_candidates:
                    search_queries.append(f"{author} {title}")
                    search_queries.append(f"{title} {author}")
        elif author_candidates and not title_candidates:
            search_queries.extend(author_candidates)

        search_queries = self._dedupe_candidates(search_queries)[:6]

        best_match, best_score, seen_asins = None, 0.0, set()
        search_region = language if language else None

        for q in search_queries:
            if not q or len(q) < 3:
                continue
            query_str = q
            if language:
                lang_name = {
                    "de": "German",
                    "fr": "French",
                    "it": "Italian",
                    "es": "Spanish",
                }.get(language, "")
                if lang_name and lang_name.lower() not in q.lower():
                    query_str = f"{q} {lang_name}"

            try:
                title_candidates_for_score = (
                    title_candidates if title_candidates else [q]
                )
                results = await list_audible_books(
                    session,
                    client_session,
                    query=query_str,
                    num_results=20,
                    audible_region=search_region,
                )
                for b in results:
                    if b.asin in seen_asins:
                        continue
                    seen_asins.add(b.asin)

                    book_title_variants = [b.title]
                    if b.subtitle:
                        book_title_variants.append(f"{b.title} {b.subtitle}")
                    if b.series:
                        book_title_variants.extend(
                            [f"{b.title} {series}" for series in b.series]
                        )

                    # Score the title (multiple variants, normalized)
                    t_score = 0.0
                    for title in title_candidates_for_score:
                        for book_title in book_title_variants:
                            t_score = max(
                                t_score, self._score_text_pair(title, book_title)
                            )

                    # Length penalty (only when book title is much shorter)
                    if title_candidates_for_score:
                        ref_title = max(
                            title_candidates_for_score,
                            key=lambda t: len(self._normalize_text(t)),
                        )
                        ref_len = len(self._normalize_text(ref_title))
                        book_len = len(self._normalize_text(b.title))
                        if ref_len and book_len and book_len < ref_len * 0.7:
                            t_score -= abs(ref_len - book_len) * 1.5

                    # Start match boost
                    boosted = False
                    for title in title_candidates_for_score:
                        title_first = self._normalize_text(title).split()[:1]
                        if not title_first:
                            continue
                        for book_title in book_title_variants:
                            if (
                                self._normalize_text(book_title).split()[:1]
                                == title_first
                            ):
                                t_score += 4
                                boosted = True
                                break
                        if boosted:
                            break

                    # Series boost if close already
                    series_score = 0.0
                    if b.series and title_candidates_for_score:
                        for title in title_candidates_for_score:
                            for series in b.series:
                                series_score = max(
                                    series_score,
                                    self._score_text_pair(title, series),
                                )
                    if series_score > 90 and t_score > 60:
                        t_score = max(t_score, series_score - 4)

                    # Score the author
                    a_score = 0.0
                    if author_candidates and b.authors:
                        for author in author_candidates:
                            for b_author in b.authors:
                                a_score = max(
                                    a_score,
                                    self._score_text_pair(author, b_author),
                                )

                    # Detect swaps
                    swap_t_score = 0.0
                    if author_candidates:
                        for author in author_candidates:
                            for book_title in book_title_variants:
                                swap_t_score = max(
                                    swap_t_score,
                                    self._score_text_pair(author, book_title),
                                )
                    swap_a_score = 0.0
                    if title_candidates and b.authors:
                        for title in title_candidates:
                            for b_author in b.authors:
                                swap_a_score = max(
                                    swap_a_score,
                                    self._score_text_pair(title, b_author),
                                )

                    is_swapped = swap_t_score > 88 and swap_a_score > 88
                    if is_swapped:
                        t_score, a_score = swap_t_score, swap_a_score

                    final_score = 0.0
                    if author_candidates:
                        author_in_title = False
                        author_in_series = False
                        for author in author_candidates:
                            if self._score_text_pair(author, b.title) > 85:
                                author_in_title = True
                                break
                        if b.series and not author_in_series:
                            for author in author_candidates:
                                if any(
                                    [
                                        self._score_text_pair(author, s) > 85
                                        for s in b.series
                                    ]
                                ):
                                    author_in_series = True
                                    break

                        if (
                            is_swapped
                            or author_in_title
                            or author_in_series
                            or t_score > 95
                        ):
                            final_score = (t_score * 0.9) + (a_score * 0.1)
                        elif a_score < 50 and t_score < 90:
                            final_score = (t_score * 0.7) + (a_score * 0.3) - 25
                        else:
                            final_score = (t_score * 0.82) + (a_score * 0.18)
                    else:
                        final_score = t_score * 0.96

                    final_score = max(0.0, min(100.0, final_score))

                    if final_score > best_score:
                        best_score, best_match = final_score, b
            except Exception as e:
                logger.debug("Hunt failed", query=query_str, error=str(e))

        if best_match and best_score > 60:
            exact_match = self._is_exact_title_author_match(
                title_candidates, author_candidates, best_match
            )
            match_score = best_score / 100.0
            if exact_match:
                match_score = 1.0
            else:
                match_score = min(match_score, 0.99)
            item.match_asin, item.match_score, item.status = (
                best_match.asin,
                match_score,
                ImportItemStatus.matched,
            )
        else:
            item.status = ImportItemStatus.missing
        session.add(item)
        try:
            session.commit()
        except:
            session.rollback()

    @staticmethod
    def find_book_path_by_asin(root: str, asin: str) -> Optional[str]:
        """
        Scans the library to find the directory containing a book with the given ASIN.
        """
        for dirpath, dirnames, filenames in os.walk(root):
            if "metadata.json" in filenames:
                try:
                    with open(
                        os.path.join(dirpath, "metadata.json"), "r", encoding="utf-8"
                    ) as f:
                        data = json.load(f)
                        if data.get("asin") == asin:
                            return dirpath
                except:
                    pass
        return None

    @staticmethod
    def map_library_asins(root: str) -> dict[str, str]:
        """
        Walks the library once and builds a mapping of ASIN -> absolute directory path.
        Extremely useful for bulk operations.
        """
        asin_map = {}
        for dirpath, dirnames, filenames in os.walk(root):
            if "metadata.json" in filenames:
                try:
                    with open(
                        os.path.join(dirpath, "metadata.json"), "r", encoding="utf-8"
                    ) as f:
                        data = json.load(f)
                        if data.get("asin"):
                            asin_map[data.get("asin")] = os.path.abspath(dirpath)
                except:
                    pass
        return asin_map
