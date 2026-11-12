"""Read an uploaded brief safely: type by content, size and page limits, text extraction only.

Nothing in an upload is ever executed. PDFs are parsed with pypdf for text only; encrypted PDFs
and PDFs without a text layer (scans) are rejected with a clear message.
"""

from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError

PDF_MAGIC = b"%PDF-"
MAX_PAGES = 200
MIN_TEXT_CHARS = 200
MIN_CHARS_PER_PAGE = 40
MAX_FILENAME_CHARS = 100
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_ALLOWED_CONTROL = {"\n", "\r", "\t"}


class UploadRejectedError(ValueError):
    """The upload is not acceptable. `status` is the HTTP status to report."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.status = status


@dataclass(frozen=True, slots=True)
class ReadBrief:
    """Text and metadata of an accepted upload."""

    filename: str
    content_type: str
    text: str


def safe_filename(name: str | None, default: str) -> str:
    """Strip directories and anything unusual; keep a short, boring name."""
    base = (name or "").replace("\\", "/").rsplit("/", 1)[-1]
    base = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    cleaned = _UNSAFE_FILENAME.sub("_", base).strip("._")[:MAX_FILENAME_CHARS]
    return cleaned or default


def read_brief(content: bytes, filename: str | None, max_bytes: int) -> ReadBrief:
    """Validate and extract text from an uploaded brief."""
    if not content:
        raise UploadRejectedError("The file is empty.")
    if len(content) > max_bytes:
        raise UploadRejectedError(f"The file is larger than {max_bytes // (1024 * 1024)} MB.", 413)
    if content.startswith(PDF_MAGIC):
        return ReadBrief(
            safe_filename(filename, "brief.pdf"), "application/pdf", _pdf_text(content)
        )
    return ReadBrief(safe_filename(filename, "brief.txt"), "text/plain", _plain_text(content))


def _plain_text(content: bytes) -> str:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UploadRejectedError("Upload a PDF or a UTF-8 text file.", 415) from exc
    if any(unicodedata.category(c) == "Cc" and c not in _ALLOWED_CONTROL for c in text):
        raise UploadRejectedError("Upload a PDF or a UTF-8 text file.", 415)
    if len(text.strip()) < MIN_TEXT_CHARS:
        raise UploadRejectedError("The brief is too short to analyse.")
    return text


def _pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content), strict=False)
        if reader.is_encrypted:
            raise UploadRejectedError("This PDF is encrypted. Upload an unprotected copy.")
        pages = reader.pages
        if len(pages) > MAX_PAGES:
            raise UploadRejectedError(f"PDFs are limited to {MAX_PAGES} pages.")
        text = "\n\n".join((page.extract_text() or "") for page in pages)
    except PdfReadError as exc:
        raise UploadRejectedError("This PDF could not be read.") from exc
    stripped = text.strip()
    if len(stripped) < MIN_TEXT_CHARS or len(stripped) < MIN_CHARS_PER_PAGE * len(pages):
        raise UploadRejectedError(
            "This PDF has little or no selectable text; it looks scanned. Upload a text-based PDF."
        )
    return text
