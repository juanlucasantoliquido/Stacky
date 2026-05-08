"""
FA-10 — Personal style memory.

Analiza los outputs aprobados de un operador y deriva su perfil de preferencias:
- length_pref: "concise" | "balanced" | "thorough"
- depth_pref: "high-level" | "balanced" | "detailed"
- format_pref: hints sobre qué formatos usa más (tablas, listas, código)
- avg_sections: cuántas secciones suele tener un output que aprueba

El perfil se inyecta en el system prompt como nota de calibración:
"Este operador prefiere outputs concisos con alta cantidad de tablas."

Tabla `user_style_profiles`:
  user_email, agent_type, length_pref, depth_pref, format_pref_json,
  avg_sections, computed_at, sample_size
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text

from db import Base, session_scope
from models import AgentExecution


class UserStyleProfile(Base):
    __tablename__ = "user_style_profiles"

    id = Column(Integer, primary_key=True)
    user_email = Column(String(200), nullable=False)
    agent_type = Column(String(20), nullable=False)
    length_pref = Column(String(20), default="balanced")
    depth_pref = Column(String(20), default="balanced")
    format_hints_json = Column(Text)
    avg_sections = Column(Float, default=3.0)
    avg_word_count = Column(Float, default=400.0)
    computed_at = Column(DateTime, default=datetime.utcnow)
    sample_size = Column(Integer, default=0)

    __table_args__ = (
        Index("ix_style_profile_user_agent", "user_email", "agent_type"),
    )

    def format_hints(self) -> dict:
        if not self.format_hints_json:
            return {}
        try:
            return json.loads(self.format_hints_json)
        except Exception:
            return {}

    def to_dict(self) -> dict:
        return {
            "user_email": self.user_email,
            "agent_type": self.agent_type,
            "length_pref": self.length_pref,
            "depth_pref": self.depth_pref,
            "format_hints": self.format_hints(),
            "avg_sections": round(self.avg_sections or 3, 1),
            "avg_word_count": round(self.avg_word_count or 400, 0),
            "computed_at": self.computed_at.isoformat() if self.computed_at else None,
            "sample_size": self.sample_size or 0,
        }

    def to_prompt_note(self) -> str:
        hints = self.format_hints()
        likes: list[str] = []
        if hints.get("tables_ratio", 0) > 0.5:
            likes.append("tablas markdown")
        if hints.get("code_ratio", 0) > 0.4:
            likes.append("bloques de código")
        if hints.get("lists_ratio", 0) > 0.5:
            likes.append("listas detalladas")
        fmt_str = ", ".join(likes) if likes else "formato estándar"
        return (
            f"## Nota de calibración para este operador\n"
            f"Preferencia de longitud: **{self.length_pref}** "
            f"(promedio {self.avg_word_count:.0f} palabras, {self.avg_sections:.0f} secciones). "
            f"Formato favorito: {fmt_str}. "
            f"Calibrá tu respuesta acordemente.\n"
        )


@dataclass
class _Features:
    word_count: int
    section_count: int
    has_tables: bool
    has_code: bool
    has_lists: bool


def _extract(text: str) -> _Features:
    words = len(text.split())
    sections = len(re.findall(r"^##\s+", text, re.MULTILINE))
    has_tables = bool(re.search(r"\|.*\|.*\|", text))
    has_code = "```" in text
    has_lists = bool(re.search(r"^\s*[-*]\s+", text, re.MULTILINE))
    return _Features(words, sections, has_tables, has_code, has_lists)


def compute_profile(user_email: str, agent_type: str, lookback_days: int = 60) -> dict | None:
    """Calcula y persiste el perfil de estilo del operador. Devuelve el dict."""
    cutoff = datetime.utcnow() - timedelta(days=lookback_days)
    with session_scope() as session:
        execs = (
            session.query(AgentExecution)
            .filter(
                AgentExecution.started_by == user_email,
                AgentExecution.agent_type == agent_type,
                AgentExecution.verdict == "approved",
                AgentExecution.output.isnot(None),
                AgentExecution.started_at >= cutoff,
            )
            .all()
        )
        if len(execs) < 3:
            return None

        feats = [_extract(e.output or "") for e in execs]
        avg_words = sum(f.word_count for f in feats) / len(feats)
        avg_secs = sum(f.section_count for f in feats) / len(feats)
        tables_r = sum(1 for f in feats if f.has_tables) / len(feats)
        code_r = sum(1 for f in feats if f.has_code) / len(feats)
        lists_r = sum(1 for f in feats if f.has_lists) / len(feats)

        length_pref = (
            "concise" if avg_words < 250
            else "thorough" if avg_words > 600
            else "balanced"
        )
        depth_pref = (
            "high-level" if avg_secs < 2
            else "detailed" if avg_secs > 5
            else "balanced"
        )

        profile = (
            session.query(UserStyleProfile)
            .filter_by(user_email=user_email, agent_type=agent_type)
            .first()
        )
        if profile is None:
            profile = UserStyleProfile(user_email=user_email, agent_type=agent_type)
            session.add(profile)
        profile.length_pref = length_pref
        profile.depth_pref = depth_pref
        profile.format_hints_json = json.dumps(
            {"tables_ratio": round(tables_r, 2),
             "code_ratio": round(code_r, 2),
             "lists_ratio": round(lists_r, 2)}
        )
        profile.avg_sections = avg_secs
        profile.avg_word_count = avg_words
        profile.computed_at = datetime.utcnow()
        profile.sample_size = len(execs)
        session.flush()
        return profile.to_dict()


def get_profile(user_email: str, agent_type: str) -> UserStyleProfile | None:
    with session_scope() as session:
        return (
            session.query(UserStyleProfile)
            .filter_by(user_email=user_email, agent_type=agent_type)
            .first()
        )


def style_prompt_note(user_email: str, agent_type: str) -> str | None:
    """Devuelve la nota de calibración para inyectar en system prompt.
    Si el perfil no existe o sample_size < 3, devuelve None."""
    p = get_profile(user_email, agent_type)
    if p is None or (p.sample_size or 0) < 3:
        return None
    return p.to_prompt_note()
