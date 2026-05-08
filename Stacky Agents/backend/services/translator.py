"""
FA-22 — Output translator (es/en/pt).

Traduce un output existente sin volver a correr al agente original.
Usa el mismo bridge de LLM con un prompt de traducción focalizado en
preservar markdown / código / nombres propios.

En modo mock devuelve un wrapper para validar la UI.
Cache por hash(output, target_lang).
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from datetime import datetime

import copilot_bridge
from config import config
from db import Base, session_scope


log = logging.getLogger(__name__)

SUPPORTED_LANGS = {
    "en": "English",
    "es": "Spanish",
    "pt": "Portuguese (Brazilian)",
}


class TranslationCache(Base):
    __tablename__ = "translation_cache"

    id = Column(Integer, primary_key=True)
    cache_key = Column(String(64), unique=True, nullable=False)
    target_lang = Column(String(8), nullable=False)
    output = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (Index("ix_translation_cache_lang", "target_lang"),)


@dataclass
class TranslationResult:
    target_lang: str
    output: str
    from_cache: bool

    def to_dict(self) -> dict:
        return {
            "target_lang": self.target_lang,
            "output": self.output,
            "from_cache": self.from_cache,
        }


def _key(output: str, target: str) -> str:
    return hashlib.sha256(f"{target}|{output}".encode("utf-8")).hexdigest()


def translate(*, output: str, target_lang: str) -> TranslationResult:
    target_lang = target_lang.lower().strip()
    if target_lang not in SUPPORTED_LANGS:
        raise ValueError(f"unsupported lang: {target_lang} (supported: {list(SUPPORTED_LANGS)})")

    if not output or not output.strip():
        return TranslationResult(target_lang=target_lang, output=output, from_cache=False)

    key = _key(output, target_lang)

    # Cache lookup
    with session_scope() as session:
        cached = session.query(TranslationCache).filter_by(cache_key=key).first()
        if cached:
            return TranslationResult(
                target_lang=target_lang, output=cached.output, from_cache=True
            )

    if config.LLM_BACKEND.lower() == "mock":
        # Mock: agrega prefijo + el original (visible para validar la UI).
        translated = (
            f"[mock translation → {SUPPORTED_LANGS[target_lang]}]\n\n{output}"
        )
    else:
        system = (
            "You are a professional translator specialized in technical documentation. "
            "Translate the user's markdown output to "
            f"{SUPPORTED_LANGS[target_lang]}. RULES: preserve markdown structure, code "
            "blocks, file paths, identifiers and acronyms. Do NOT translate code or "
            "proper nouns. Keep the same heading hierarchy."
        )
        try:
            resp = copilot_bridge.invoke(
                agent_type="__translator__",
                system=system,
                user=output,
                on_log=lambda *a, **k: None,
            )
            translated = resp.text or output
        except Exception as exc:  # noqa: BLE001
            log.warning("translator failed: %s — returning original", exc)
            translated = output

    with session_scope() as session:
        session.add(TranslationCache(
            cache_key=key, target_lang=target_lang, output=translated
        ))

    return TranslationResult(
        target_lang=target_lang, output=translated, from_cache=False
    )
