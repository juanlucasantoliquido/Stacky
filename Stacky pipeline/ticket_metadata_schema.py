"""
ticket_metadata_schema.py — Schemas Pydantic para metadata de tickets Stacky.

Define los modelos de colores y tags de usuario que se persisten en
``data/ticket_metadata.json`` (schema v1).

Auto-detecta Pydantic v1 o v2 — el shim expone siempre ``field_validator``,
``model_dump`` y ``ConfigDict`` con semántica v2.

Reglas de validación (confirmadas en FASE 1):
    * color       : exactamente "#rrggbb" (6 hex, minúsculas se normalizan)
    * tags        : cada tag en [a-záéíóúñ0-9_-], 1..32 chars
    * tags/ticket : máximo 20, dedup preservando orden, lowercase + trim
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ── Pydantic v1/v2 auto-detect shim ───────────────────────────────────────────
try:
    from pydantic import VERSION as _PYDANTIC_VERSION  # type: ignore[attr-defined]
    _PYDANTIC_MAJOR = int(str(_PYDANTIC_VERSION).split(".", 1)[0])
except Exception:  # pragma: no cover
    _PYDANTIC_MAJOR = 1

if _PYDANTIC_MAJOR >= 2:
    from pydantic import BaseModel, ConfigDict, Field, field_validator  # type: ignore
    _PYDANTIC_V2 = True
else:  # pragma: no cover — path de compatibilidad
    from pydantic import BaseModel, Field, validator as _v1_validator  # type: ignore
    _PYDANTIC_V2 = False

    def field_validator(*fields, mode: str = "after"):  # type: ignore[no-redef]
        """Shim: traduce field_validator(v2) → validator(v1, pre=mode=='before')."""
        return _v1_validator(*fields, pre=(mode == "before"), allow_reuse=True)

    class ConfigDict(dict):  # type: ignore[no-redef]
        pass


_COLOR_RE = re.compile(r"^#[0-9a-f]{6}$")
_TAG_RE = re.compile(r"^[a-záéíóúñ0-9_\-]+$")

MAX_TAGS_PER_TICKET = 20
MAX_TAG_LENGTH = 32


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_tag(raw: str) -> str:
    return (raw or "").strip().lower()


class TicketColor(BaseModel):
    """Color custom de un ticket (#rrggbb)."""
    if _PYDANTIC_V2:
        model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    hex: str = Field(..., description="Formato #rrggbb (lowercase).")

    @field_validator("hex", mode="before")
    def _normalize_hex(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise ValueError("color.hex debe ser string #rrggbb")
        s = v.strip().lower()
        if not _COLOR_RE.match(s):
            raise ValueError(f"color inválido: {v!r} (esperado #rrggbb)")
        return s


class TicketUserTags(BaseModel):
    """Tags de usuario asociados a un ticket (free-text normalizado)."""
    if _PYDANTIC_V2:
        model_config = ConfigDict(extra="ignore")

    tags: List[str] = Field(default_factory=list)

    @field_validator("tags", mode="before")
    def _normalize_tags(cls, v: Any) -> List[str]:
        if v is None:
            return []
        if not isinstance(v, list):
            raise ValueError("tags debe ser una lista de strings")
        seen: set = set()
        out: List[str] = []
        for raw in v:
            if not isinstance(raw, str):
                continue
            tag = _normalize_tag(raw)
            if not tag:
                continue
            if len(tag) > MAX_TAG_LENGTH:
                raise ValueError(f"tag excede {MAX_TAG_LENGTH} chars: {tag!r}")
            if not _TAG_RE.match(tag):
                raise ValueError(f"tag inválido: {tag!r} (chars permitidos: a-záéíóúñ0-9_-)")
            if tag in seen:
                continue
            seen.add(tag)
            out.append(tag)
        if len(out) > MAX_TAGS_PER_TICKET:
            raise ValueError(f"máx {MAX_TAGS_PER_TICKET} tags por ticket (recibidos {len(out)})")
        return out


class TicketMetadata(BaseModel):
    """Metadata persistida por ticket."""
    if _PYDANTIC_V2:
        model_config = ConfigDict(extra="ignore")

    ticket_id: str
    color: Optional[TicketColor] = None
    user_tags: TicketUserTags = Field(default_factory=TicketUserTags)
    # Metadata derivada del indexador (FASE 2)
    commits_count: Optional[int] = None
    last_commit_hash: Optional[str] = None
    last_commit_at: Optional[str] = None
    ado_comments_count: Optional[int] = None
    notes_count: Optional[int] = None
    last_note_at: Optional[str] = None
    last_indexed_at: Optional[str] = None
    # Timestamps
    updated_at: str = Field(default_factory=_utc_now_iso)

    def to_dict(self) -> Dict[str, Any]:
        if _PYDANTIC_V2:
            return self.model_dump(mode="json", exclude_none=False)
        return self.dict()  # type: ignore[attr-defined]


class TicketMetadataStore(BaseModel):
    """Wrapper raíz del archivo JSON ``data/ticket_metadata.json``."""
    if _PYDANTIC_V2:
        model_config = ConfigDict(extra="ignore")

    version: int = 1
    tickets: Dict[str, TicketMetadata] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        if _PYDANTIC_V2:
            return self.model_dump(mode="json")
        return self.dict()  # type: ignore[attr-defined]
