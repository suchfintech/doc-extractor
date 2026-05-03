"""PDF → image preprocessing for the vision pipeline (AR4).

Vision agents only consume images. PDFs are rendered to PNGs via PyMuPDF at
150 DPI — readable for OCR/vision while keeping per-page payloads small
enough that BankStatement multi-page batches stay within model context and
cost budgets.

``mode`` is the per-document-type knob (see ``vision_path._pdf_mode_for``):
``"page1"`` is the v1 default for single-page document types like Passport;
``"all_pages"`` is reserved for the BankStatement specialist landing in
Epic 5.
"""

from __future__ import annotations

from typing import Any, Literal

import pymupdf as _pymupdf

from doc_extractor.exceptions import PDFConversionError

# pymupdf ships no type stubs; cast to Any so the typed call-sites below stay
# expressive without a per-line `# type: ignore[no-untyped-call]` chorus.
pymupdf: Any = _pymupdf

PdfMode = Literal["page1", "all_pages"]

DEFAULT_RENDER_DPI = 150


def pdf_to_images(pdf_bytes: bytes, mode: PdfMode = "page1") -> list[bytes]:
    """Render a PDF to PNG bytes, one entry per included page.

    Args:
        pdf_bytes: The raw PDF payload.
        mode: ``"page1"`` returns only page 1 (1 element); ``"all_pages"``
            returns every page in document order.

    Raises:
        PDFConversionError: Empty input, malformed PDF, or render failure.
    """
    if not pdf_bytes:
        raise PDFConversionError("pdf_to_images received empty bytes")

    try:
        doc = pymupdf.Document(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise PDFConversionError(f"failed to open PDF: {exc}") from exc

    if doc.page_count == 0:
        doc.close()
        raise PDFConversionError("PDF has zero pages")

    page_indices = [0] if mode == "page1" else range(doc.page_count)
    try:
        return [
            doc[idx].get_pixmap(dpi=DEFAULT_RENDER_DPI).tobytes("png")
            for idx in page_indices
        ]
    except Exception as exc:
        raise PDFConversionError(f"failed to render PDF page: {exc}") from exc
    finally:
        doc.close()
