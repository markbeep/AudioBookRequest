from app.internal.indexers.mam_models import _Result
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString
import re

def generate_opf_for_mam(result: _Result) -> str:
    """
    Generates OPF metadata content for a MAM result.
    """
    
    package = Element('package', version='2.0', xmlns='http://www.idpf.org/2007/opf', unique_identifier='bookid')
    
    metadata = SubElement(package, 'metadata', {
        'xmlns:dc': 'http://purl.org/dc/elements/1.1/', 
        'xmlns:opf': 'http://www.idpf.org/2007/opf'
    })
    
    # Basic info
    title = result.book_title or result.title or "Unknown"
    SubElement(metadata, 'dc:title').text = title
    
    for author in result.authors:
        SubElement(metadata, 'dc:creator', {'opf:role': 'aut', 'opf:file-as': author}).text = author
    
    for narrator in result.narrators:
        SubElement(metadata, 'dc:contributor', {'opf:role': 'nrt', 'opf:file-as': narrator}).text = narrator
    
    if result.synopsis:
        clean_text = re.sub('<[^<]+?>', '', result.synopsis)
        SubElement(metadata, 'dc:description').text = clean_text
    
    if result.filetype:
        SubElement(metadata, 'dc:format').text = result.filetype.upper()
    
    for lang in result.languages:
        SubElement(metadata, 'dc:language').text = lang
    
    if result.added:
        try:
            date_part = result.added.split(' ')[0]
            SubElement(metadata, 'dc:date').text = date_part
        except Exception:
            pass

    SubElement(metadata, 'dc:identifier', id='bookid', system='MAM').text = str(result.id)

    if result.tags:
        for tag in result.tags.split(','):
            SubElement(metadata, 'dc:subject').text = tag.strip()
    
    # Series and indexing
    if result.series:
        for s_info in result.series:
            if " #" in s_info:
                name, idx = s_info.split(" #", 1)
                SubElement(metadata, 'meta', {'name': 'calibre:series', 'content': name})
                SubElement(metadata, 'meta', {'name': 'calibre:series_index', 'content': idx})
            else:
                SubElement(metadata, 'meta', {'name': 'calibre:series', 'content': s_info})
    
    SubElement(metadata, 'meta', {'name': 'calibre:rating', 'content': '10'})

    if result.synopsis_image:
        SubElement(metadata, 'meta', {'name': 'cover', 'content': 'cover-image'})

    # Manifest and spine setup
    manifest = SubElement(package, 'manifest')
    if result.synopsis_image:
        SubElement(manifest, 'item', id='cover-image', href=result.synopsis_image, media_type='image/jpeg')
    
    SubElement(manifest, 'item', id='ncx', href='toc.ncx', media_type='application/x-dtbncx+xml')
    SubElement(manifest, 'item', id='text', href='dummy.html', media_type='application/xhtml+xml')
    
    spine = SubElement(package, 'spine', toc='ncx')
    SubElement(spine, 'itemref', idref='text')

    # Formatting
    xml_str = tostring(package, 'utf-8')
    dom = parseString(xml_str)
    return dom.toprettyxml(indent="  ")
