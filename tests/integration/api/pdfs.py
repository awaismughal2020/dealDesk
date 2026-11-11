"""Build small PDFs for upload tests (a text PDF, an encrypted one, a scan-like one)."""

from __future__ import annotations

import io

from pypdf import PdfReader, PdfWriter


def text_pdf(lines: list[str]) -> bytes:
    """A one-page PDF with real text, built by hand with correct xref offsets."""

    def esc(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    content = (
        "BT /F1 10 Tf 40 760 Td 14 TL " + " ".join(f"({esc(line)}) '" for line in lines) + " ET"
    )
    objects = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        f"<< /Length {len(content)} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return bytes(out)


def encrypted_pdf(lines: list[str]) -> bytes:
    """The text PDF, password protected."""
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(text_pdf(lines))))
    writer.encrypt("sample-owner-password")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def blank_pdf() -> bytes:
    """A page with no text layer (what a scan looks like to a text extractor)."""
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
