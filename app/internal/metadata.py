import json
import os
import re
from typing import Optional
from sqlmodel import Session
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString

from app.internal.models import Audiobook
from app.internal.indexers.mam_models import _Result


async def generate_abs_metadata(
    book: Audiobook, dest_path: str, mam_result: Optional[_Result] = None
):
    """
    Generates Audiobookshelf compatible metadata.json
    """
    metadata = {
        "title": book.title,
        "subtitle": book.subtitle,
        "authors": book.authors,
        "narrators": book.narrators,
        "series": book.series,
        "genres": getattr(book, "genres", []),
        "publishedYear": str(book.release_date.year) if book.release_date else None,
        "publishedDate": book.release_date.isoformat() if book.release_date else None,
        "publisher": getattr(book, "publisher", None),
        "description": getattr(book, "description", None),
        "asin": book.asin,
        "language": getattr(book, "language", None),
    }

    if mam_result:
        if mam_result.synopsis:
            metadata["description"] = re.sub("<[^<]+?>", "", mam_result.synopsis)
        if mam_result.tags:
            metadata["genres"] = list(
                set(
                    metadata["genres"] + [t.strip() for t in mam_result.tags.split(",")]
                )
            )

    file_path = os.path.join(dest_path, "metadata.json")
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=4, ensure_ascii=False)


async def generate_opf_metadata(
    session: Session,
    book: Audiobook,
    dest_path: str,
    mam_result: Optional[_Result] = None,
):
    """
    Generates OPF metadata for the book.
    """
    if mam_result:
        opf_content = generate_opf_for_mam(mam_result)
    else:
        opf_content = generate_opf_basic(book)

    file_path = os.path.join(dest_path, "metadata.opf")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(opf_content)


def generate_opf_basic(book: Audiobook) -> str:
    """
    Generates a basic OPF metadata content for an Audiobook.
    """
    package = Element(
        "package",
        version="2.0",
        xmlns="http://www.idpf.org/2007/opf",
        unique_identifier="bookid",
    )

    metadata = SubElement(
        package,
        "metadata",
        {
            "xmlns:dc": "http://purl.org/dc/elements/1.1/",
            "xmlns:opf": "http://www.idpf.org/2007/opf",
        },
    )

    # Basic info
    SubElement(metadata, "dc:title").text = book.title

    for author in book.authors:
        SubElement(
            metadata, "dc:creator", {"opf:role": "aut", "opf:file-as": author}
        ).text = author

    for narrator in book.narrators:
        SubElement(
            metadata, "dc:contributor", {"opf:role": "nrt", "opf:file-as": narrator}
        ).text = narrator

    if book.subtitle:
        SubElement(metadata, "dc:description").text = book.subtitle

    # Series
    if book.series:
        for s_info in book.series:
            if " #" in s_info:
                name, idx = s_info.split(" #", 1)
                SubElement(
                    metadata, "meta", {"name": "calibre:series", "content": name}
                )
                SubElement(
                    metadata, "meta", {"name": "calibre:series_index", "content": idx}
                )
            else:
                SubElement(
                    metadata, "meta", {"name": "calibre:series", "content": s_info}
                )

    if book.release_date:
        SubElement(metadata, "dc:date").text = book.release_date.isoformat().split("T")[
            0
        ]

    SubElement(metadata, "dc:identifier", id="bookid", system="ASIN").text = book.asin

    # Manifest and spine setup (minimal)
    manifest = SubElement(package, "manifest")
    SubElement(
        manifest,
        "item",
        id="ncx",
        href="toc.ncx",
        media_type="application/x-dtbncx+xml",
    )
    SubElement(
        manifest,
        "item",
        id="text",
        href="dummy.html",
        media_type="application/xhtml+xml",
    )

    spine = SubElement(package, "spine", toc="ncx")
    SubElement(spine, "itemref", idref="text")

    # Formatting
    xml_str = tostring(package, "utf-8")
    dom = parseString(xml_str)
    return dom.toprettyxml(indent="  ")


def generate_opf_for_mam(result: _Result) -> str:
    """
    Generates OPF metadata content for a MAM result.
    """
    package = Element(
        "package",
        version="2.0",
        xmlns="http://www.idpf.org/2007/opf",
        unique_identifier="bookid",
    )

    metadata = SubElement(
        package,
        "metadata",
        {
            "xmlns:dc": "http://purl.org/dc/elements/1.1/",
            "xmlns:opf": "http://www.idpf.org/2007/opf",
        },
    )

    # Basic info
    title = result.book_title or result.title or "Unknown"
    SubElement(metadata, "dc:title").text = title

    for author in result.authors:
        SubElement(
            metadata, "dc:creator", {"opf:role": "aut", "opf:file-as": author}
        ).text = author

    for narrator in result.narrators:
        SubElement(
            metadata, "dc:contributor", {"opf:role": "nrt", "opf:file-as": narrator}
        ).text = narrator

    if result.synopsis:
        clean_text = re.sub("<[^<]+?>", "", result.synopsis)
        SubElement(metadata, "dc:description").text = clean_text

    if result.filetype:
        SubElement(metadata, "dc:format").text = result.filetype.upper()

    for lang in result.languages:
        SubElement(metadata, "dc:language").text = lang

    if result.added:
        try:
            date_part = result.added.split(" ")[0]
            SubElement(metadata, "dc:date").text = date_part
        except Exception:
            pass

    SubElement(metadata, "dc:identifier", id="bookid", system="MAM").text = str(
        result.id
    )

    if result.tags:
        for tag in result.tags.split(","):
            SubElement(metadata, "dc:subject").text = tag.strip()

    # Series and indexing
    if result.series:
        for s_info in result.series:
            if " #" in s_info:
                name, idx = s_info.split(" #", 1)
                SubElement(
                    metadata, "meta", {"name": "calibre:series", "content": name}
                )
                SubElement(
                    metadata, "meta", {"name": "calibre:series_index", "content": idx}
                )
            else:
                SubElement(
                    metadata, "meta", {"name": "calibre:series", "content": s_info}
                )

    SubElement(metadata, "meta", {"name": "calibre:rating", "content": "10"})

    # Manifest and spine setup
    manifest = SubElement(package, "manifest")
    SubElement(
        manifest,
        "item",
        id="ncx",
        href="toc.ncx",
        media_type="application/x-dtbncx+xml",
    )
    SubElement(
        manifest,
        "item",
        id="text",
        href="dummy.html",
        media_type="application/xhtml+xml",
    )

    spine = SubElement(package, "spine", toc="ncx")
    SubElement(spine, "itemref", idref="text")

    # Formatting
    xml_str = tostring(package, "utf-8")
    dom = parseString(xml_str)
    return dom.toprettyxml(indent="  ")
