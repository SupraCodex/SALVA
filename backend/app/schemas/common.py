from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")
DISCLAIMER_CODE = "MODEL_ESTIMATE_NOT_FIELD_VALIDATED"


class StrictIn(BaseModel):
    """Request bodies: unknown fields are refused (extra='forbid'), strings are trimmed."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Quantiles(BaseModel):
    p10: float | None
    p50: float | None
    p90: float | None


class Sourced(BaseModel):
    """A value with its provenance (DAT-01): manual, open-meteo, reference table, assumption..."""

    value: float | None
    source: str


def normalize_email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 254 or not EMAIL_RE.match(value):
        raise ValueError("invalid e-mail address")
    return value
