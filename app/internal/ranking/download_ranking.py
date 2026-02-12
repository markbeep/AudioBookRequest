import asyncio
from functools import cmp_to_key
from typing import Callable, final

import pydantic
from aiohttp import ClientSession
from rapidfuzz import fuzz, utils
from sqlmodel import Session

from app.internal.models import Audiobook, ProwlarrSource
from app.internal.ranking.quality import quality_config
from app.internal.ranking.quality_extract import Quality, extract_qualities
from app.util.log import logger


class RankSource(pydantic.BaseModel):
    source: ProwlarrSource
    quality: Quality


async def rank_sources(
    session: Session,
    client_session: ClientSession,
    sources: list[ProwlarrSource],
    book: Audiobook,
) -> list[ProwlarrSource]:
    async def get_qualities(source: ProwlarrSource):
        qualities = await extract_qualities(session, client_session, source, book)
        return [RankSource(source=source, quality=q) for q in qualities]

    coros = [get_qualities(source) for source in sources]
    rank_sources = [x for y in await asyncio.gather(*coros) for x in y]

    compare = CompareSource(session, book)
    rank_sources.sort(key=cmp_to_key(compare))

    return [rs.source for rs in rank_sources]


@final
class CompareSource:
    def __init__(self, session: Session, book: Audiobook):
        self.session = session
        self.book = book
        self.compare_order = [
            self._compare_valid,
            self._compare_title,
            self._compare_authors,
            self._compare_narrators,
            self._compare_format,
            self._compare_flags,
            self._compare_indexer,
            self._compare_subtitle,
            self._compare_seeders,
            self._compare_age,
        ]

    def __call__(self, a: RankSource, b: RankSource):
        return self.compare(a, b)

    def compare(self, a: RankSource, b: RankSource) -> int:
        return self._get_next_compare(0)(a, b, 1)

    def _get_next_compare(
        self, index: int
    ) -> Callable[[RankSource, RankSource, int], int]:
        def default_compare(a: RankSource, b: RankSource, next_compare: int) -> int:
            _, _, _ = a, b, next_compare
            return 0

        if index < len(self.compare_order):
            return self.compare_order[index]
        return default_compare

    def _is_valid_quality(self, a: RankSource) -> bool:
        match a.quality.file_format:
            case "flac":
                quality_range = quality_config.get_range(self.session, "quality_flac")
            case "m4b":
                quality_range = quality_config.get_range(self.session, "quality_m4b")
            case "mp3":
                quality_range = quality_config.get_range(self.session, "quality_mp3")
            case "unknown-audio":
                quality_range = quality_config.get_range(
                    self.session, "quality_unknown_audio"
                )
            case "unknown":
                quality_range = quality_config.get_range(
                    self.session, "quality_unknown"
                )

        return quality_range.from_kbits < a.quality.kbits < quality_range.to_kbits

    def _has_minimum_match(self, a: RankSource) -> bool:
        """Check if source has at least a minimal match with the book.

        Requires either:
        - Title match, OR
        - At least one author/narrator match
        """
        title_ratio = quality_config.get_title_exists_ratio(self.session)
        name_ratio = quality_config.get_name_exists_ratio(self.session)

        # Check title match
        title_match = exists_in_title(
            self.book.title,
            a.source.title,
            title_ratio,
        )

        if title_match:
            logger.debug(
                "Title matches",
                book_title=self.book.title,
                source_title=a.source.title,
                ratio=title_ratio,
            )
            return True

        # Check author/narrator match
        author_score = max(
            vaguely_exist_in_title(
                self.book.authors,
                a.source.title,
                name_ratio,
            ),
            fuzzy_author_narrator_match(
                a.source.book_metadata.authors,
                self.book.authors,
                name_ratio,
            ),
        )

        narrator_score = max(
            vaguely_exist_in_title(
                self.book.narrators,
                a.source.title,
                name_ratio,
            ),
            fuzzy_author_narrator_match(
                a.source.book_metadata.narrators,
                self.book.narrators,
                name_ratio,
            ),
        )

        # Require at least one author OR one narrator match
        return author_score > 0 or narrator_score > 0

    def _compare_valid(self, a: RankSource, b: RankSource, next_compare: int) -> int:
        """Filter out any reasons that make it not valid"""
        if a.source.protocol == "torrent":
            a_valid = self._is_valid_quality(
                a
            ) and a.source.seeders >= quality_config.get_min_seeders(self.session)
        else:
            a_valid = self._is_valid_quality(a)

        if b.source.protocol == "torrent":
            b_valid = self._is_valid_quality(
                b
            ) and b.source.seeders >= quality_config.get_min_seeders(self.session)
        else:
            b_valid = self._is_valid_quality(b)

        # Check if the source has a reasonable match with the book
        # Require either title match OR (author/narrator match)
        a_valid = a_valid and self._has_minimum_match(a)
        b_valid = b_valid and self._has_minimum_match(b)

        if a_valid == b_valid:
            return self._get_next_compare(next_compare)(a, b, next_compare + 1)
        return int(b_valid) - int(a_valid)

    def _compare_format(self, a: RankSource, b: RankSource, next_compare: int) -> int:
        if a.quality.file_format == b.quality.file_format:
            return self._get_next_compare(next_compare)(a, b, next_compare + 1)
        a_index = quality_config.calculate_quality_rank(
            self.session, a.quality.file_format
        )
        b_index = quality_config.calculate_quality_rank(
            self.session, b.quality.file_format
        )
        return a_index - b_index

    def _compare_flags(self, a: RankSource, b: RankSource, next_compare: int) -> int:
        a_score = sum(
            f.score
            for f in quality_config.get_indexer_flags(self.session)
            if f.flag.lower() in a.source.indexer_flags
        )
        b_score = sum(
            f.score
            for f in quality_config.get_indexer_flags(self.session)
            if f.flag.lower() in b.source.indexer_flags
        )
        if a_score == b_score:
            return self._get_next_compare(next_compare)(a, b, next_compare + 1)
        return b_score - a_score

    def _compare_indexer(self, a: RankSource, b: RankSource, next_compare: int) -> int:
        a_index = quality_config.calculate_indexer_rank(
            self.session, a.source.indexer_id
        )
        b_index = quality_config.calculate_indexer_rank(
            self.session, b.source.indexer_id
        )
        if a_index == b_index:
            return self._get_next_compare(next_compare)(a, b, next_compare + 1)
        return a_index - b_index

    def _compare_title(self, a: RankSource, b: RankSource, next_compare: int) -> int:
        a_title = exists_in_title(
            self.book.title,
            a.source.title,
            quality_config.get_title_exists_ratio(self.session),
        )
        b_title = exists_in_title(
            self.book.title,
            b.source.title,
            quality_config.get_title_exists_ratio(self.session),
        )
        if a_title == b_title:
            return self._get_next_compare(next_compare)(a, b, next_compare + 1)
        return int(b_title) - int(a_title)

    def _compare_subtitle(self, a: RankSource, b: RankSource, next_compare: int) -> int:
        if not self.book.subtitle:
            return self._get_next_compare(next_compare)(a, b, next_compare + 1)
        a_title = exists_in_title(
            self.book.subtitle,
            a.source.title,
            quality_config.get_title_exists_ratio(self.session),
        )
        b_title = exists_in_title(
            self.book.subtitle,
            b.source.title,
            quality_config.get_title_exists_ratio(self.session),
        )
        if a_title == b_title:
            return self._get_next_compare(next_compare)(a, b, next_compare + 1)
        return int(b_title) - int(a_title)

    def _compare_authors(self, a: RankSource, b: RankSource, next_compare: int) -> int:
        a_score = max(
            vaguely_exist_in_title(
                self.book.authors,
                a.source.title,
                quality_config.get_name_exists_ratio(self.session),
            ),
            fuzzy_author_narrator_match(
                a.source.book_metadata.authors,
                self.book.authors,
                quality_config.get_name_exists_ratio(self.session),
            ),
        )
        b_score = max(
            vaguely_exist_in_title(
                self.book.authors,
                b.source.title,
                quality_config.get_name_exists_ratio(self.session),
            ),
            fuzzy_author_narrator_match(
                b.source.book_metadata.authors,
                self.book.authors,
                quality_config.get_name_exists_ratio(self.session),
            ),
        )
        if a_score == b_score:
            return self._get_next_compare(next_compare)(a, b, next_compare + 1)
        return b_score - a_score

    def _compare_narrators(
        self, a: RankSource, b: RankSource, next_compare: int
    ) -> int:
        a_score = max(
            vaguely_exist_in_title(
                self.book.narrators,
                a.source.title,
                quality_config.get_name_exists_ratio(self.session),
            ),
            fuzzy_author_narrator_match(
                a.source.book_metadata.narrators,
                self.book.narrators,
                quality_config.get_name_exists_ratio(self.session),
            ),
        )
        b_score = max(
            vaguely_exist_in_title(
                self.book.narrators,
                b.source.title,
                quality_config.get_name_exists_ratio(self.session),
            ),
            fuzzy_author_narrator_match(
                b.source.book_metadata.narrators,
                self.book.narrators,
                quality_config.get_name_exists_ratio(self.session),
            ),
        )
        if a_score == b_score:
            return self._get_next_compare(next_compare)(a, b, next_compare + 1)
        return b_score - a_score

    def _compare_seeders(self, a: RankSource, b: RankSource, next_compare: int) -> int:
        if a.source.protocol == "usenet" or b.source.protocol == "usenet":
            return self._get_next_compare(next_compare)(a, b, next_compare + 1)
        if a.source.seeders == b.source.seeders:
            return self._get_next_compare(next_compare)(a, b, next_compare + 1)
        return b.source.seeders - a.source.seeders

    def _compare_age(self, a: RankSource, b: RankSource, next_compare: int) -> int:
        if a.source.protocol != b.source.protocol:
            return self._get_next_compare(next_compare)(a, b, next_compare + 1)
        if a.source.protocol == "usenet":
            # With usenets: newer => better
            return int((a.source.publish_date - b.source.publish_date).total_seconds())
        # With torrents: older => better
        return int((b.source.publish_date - a.source.publish_date).total_seconds())


def fuzzy_author_narrator_match(
    source_people: list[str], book_people: list[str], name_exists_ratio: int
) -> int:
    """Calculate a fuzzy matching score between two lists of author/narrator names."""
    if not source_people or not book_people:
        return 0
    score = 0
    for book_person in book_people:
        best_match = 0.0
        for source_person in source_people:
            match_score = fuzz.token_set_ratio(
                book_person, source_person, processor=utils.default_process
            )
            best_match = max(best_match, match_score)

        # Only count matches above threshold
        if best_match > name_exists_ratio:
            score += 1

    return score


def vaguely_exist_in_title(words: list[str], title: str, name_exists_ratio: int) -> int:
    return sum(
        1
        for w in words
        if fuzz.token_set_ratio(w, title, processor=utils.default_process)
        > name_exists_ratio
    )


def exists_in_title(word: str, title: str, title_exists_ratio: int) -> bool:
    return (
        fuzz.partial_ratio(word, title, processor=utils.default_process)
        > title_exists_ratio
    )
