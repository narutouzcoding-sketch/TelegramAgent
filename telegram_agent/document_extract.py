"""Bounded text extraction in a separate process; never executes document contents."""

import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

MAX_TEXT = 80000


def extract(path):
    if path.stat().st_size > 5 * 1024 * 1024:
        raise ValueError("Fayl 5 MB dan katta")
    if path.suffix.lower() in {".txt", ".md"}:
        raw = path.read_bytes()
        text = raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")
    elif path.suffix.lower() == ".docx":
        with zipfile.ZipFile(path) as archive:
            item = archive.getinfo("word/document.xml")
            if item.file_size > 2 * 1024 * 1024 or len(archive.infolist()) > 2000:
                raise ValueError("DOCX hajmi juda katta")
            xml = ElementTree.fromstring(archive.read(item))
            text = "\n".join(
                "".join(p.itertext())
                for p in xml.iter("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p")
            )
    elif path.suffix.lower() == ".pdf":
        from pypdf import PdfReader, overwrite_configuration

        overwrite_configuration(
            zlib_maximum_output_length=2 * 1024 * 1024,
            lzw_maximum_output_length=2 * 1024 * 1024,
            maximum_declared_stream_length=5 * 1024 * 1024,
            array_based_stream_maximum_output_length=5 * 1024 * 1024,
        )
        reader = PdfReader(path, strict=True)
        if reader.is_encrypted:
            raise ValueError("PDF parollangan")
        if len(reader.pages) > 50:
            raise ValueError("PDF 50 sahifadan katta")
        parts = []
        for i, page in enumerate(reader.pages):
            page_text = (page.extract_text() or "").strip()
            if page_text:
                parts.append(f"[Sahifa {i + 1}]\n" + page_text)
            if sum(map(len, parts)) > MAX_TEXT:
                break
        text = "\n\n".join(parts)
    else:
        raise ValueError("Format qo'llanmaydi")
    return text[:MAX_TEXT].replace("\x00", "")


if __name__ == "__main__":
    try:
        print(json.dumps({"text": extract(Path(sys.argv[1]))}, ensure_ascii=True))
    except Exception as exc:
        print(json.dumps({"error": type(exc).__name__}))
