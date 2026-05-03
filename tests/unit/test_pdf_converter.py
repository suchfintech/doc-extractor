"""Unit tests for ``pdf.converter.pdf_to_images`` (Story 3.3)."""

from __future__ import annotations

from typing import Any

import pymupdf as _pymupdf
import pytest

from doc_extractor.exceptions import PDFConversionError
from doc_extractor.pdf.converter import pdf_to_images

pymupdf: Any = _pymupdf

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _make_pdf(num_pages: int) -> bytes:
    """Build a synthetic in-memory PDF with ``num_pages`` A4 pages of small text."""
    doc = pymupdf.Document()
    for i in range(num_pages):
        page = doc.new_page(width=595, height=842)  # A4 in points
        page.insert_text((50, 100), f"page {i + 1}")
    payload: bytes = doc.tobytes()
    doc.close()
    return payload


def test_page1_mode_returns_single_png() -> None:
    pdf = _make_pdf(1)
    pages = pdf_to_images(pdf, mode="page1")
    assert len(pages) == 1
    assert pages[0].startswith(PNG_MAGIC)


def test_page1_mode_returns_only_first_of_multipage_pdf() -> None:
    pdf = _make_pdf(3)
    pages = pdf_to_images(pdf, mode="page1")
    assert len(pages) == 1
    assert pages[0].startswith(PNG_MAGIC)


def test_all_pages_mode_returns_one_png_per_page() -> None:
    pdf = _make_pdf(3)
    pages = pdf_to_images(pdf, mode="all_pages")
    assert len(pages) == 3
    assert all(page.startswith(PNG_MAGIC) for page in pages)


def test_pages_are_non_empty_bytes() -> None:
    pdf = _make_pdf(2)
    pages = pdf_to_images(pdf, mode="all_pages")
    assert all(len(page) > len(PNG_MAGIC) for page in pages)


def test_default_mode_is_page1() -> None:
    pdf = _make_pdf(2)
    assert len(pdf_to_images(pdf)) == 1


def test_empty_bytes_raises_pdf_conversion_error() -> None:
    with pytest.raises(PDFConversionError, match="empty"):
        pdf_to_images(b"")


def test_corrupt_pdf_raises_pdf_conversion_error() -> None:
    with pytest.raises(PDFConversionError, match="failed to open"):
        pdf_to_images(b"not a pdf at all" * 16)
