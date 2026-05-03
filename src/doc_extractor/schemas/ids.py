"""ID-document schemas.

`IDDocBase` carries the fields shared across government-issued IDs (passport,
driver licence, national ID, visa). `Passport` adds passport-specific fields
including the two MRZ lines.

All date fields use the `YYYY-MM-DD` string format and follow the
empty-string-not-null convention defined on `Frontmatter`.
"""
from __future__ import annotations

from doc_extractor.schemas.base import Frontmatter


class IDDocBase(Frontmatter):
    doc_number: str | None = ""
    dob: str | None = ""
    issue_date: str | None = ""
    expiry_date: str | None = ""
    place_of_birth: str | None = ""
    sex: str | None = ""


class Passport(IDDocBase):
    passport_number: str | None = ""
    nationality: str | None = ""
    mrz_line_1: str | None = ""
    mrz_line_2: str | None = ""


class DriverLicence(IDDocBase):
    licence_class: str | None = ""
    licence_endorsements: str | None = ""
    licence_restrictions: str | None = ""
    address: str | None = ""


class NationalID(IDDocBase):
    nationality: str | None = ""
    id_card_number: str | None = ""
    issuing_authority: str | None = ""
    address: str | None = ""
