"""Comment Indexer para PM Intelligence Suite — Fase 1 MVP.

Toma comentarios de work items vía `AdoClient.fetch_comments`, los normaliza
(HTML strip + PII mask) y los persiste en `pm_work_item_comments`.

Garantías:
- El texto crudo (HTML + PII) NO se persiste. Solo el `text_plain` ya sanitizado.
- Idempotencia: la combinación (ado_id, author, comment_date, hash(text_plain))
  es única — re-indexar el mismo comentario no duplica.
- Sin IA. Los campos `sentiment_*` y `ai_analyzed` quedan en valores neutros
  hasta que Fase 2 pase los eval fixtures (§5 plan v2).

NO modifica work items en ADO. Solo lectura.
"""
from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import date, datetime
from html.parser import HTMLParser

from sqlalchemy.exc import OperationalError

from services.ado_client import AdoApiError, AdoClient
from services.pii_masker import mask_text

_PERSIST_MAX_RETRIES = 3
_PERSIST_BACKOFF_BASE = 0.1

logger = logging.getLogger("stacky_agents.pm.comment_indexer")


# ── HTML → texto plano ────────────────────────────────────────────────────────

class _HtmlStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def handle_starttag(self, tag, attrs):  # noqa: ARG002
        if tag in {"br", "p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")


def html_to_text(html: str) -> str:
    """Convierte HTML de ADO a texto plano normalizado.

    Replica la lógica de services/ado_sync._html_to_text — duplicada acá a
    propósito para mantener el módulo PM autocontenido y evitar acoplar
    cambios futuros del sync general.
    """
    if not html:
        return ""
    parser = _HtmlStripper()
    try:
        parser.feed(html)
    except Exception:
        return re.sub(r"<[^>]+>", " ", html).strip()
    text = "".join(parser.parts)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ── sanitización completa de un comentario ─────────────────────────────────────

def sanitize_comment_text(raw_html: str) -> str:
    """HTML strip + PII mask. Devuelve SOLO el texto seguro para persistir.

    El `mask_map` se descarta intencionalmente: nunca persistimos PII original,
    ni el map reversible, porque los comentarios PM son consumidos como texto
    plano agregado (no requieren unmask).
    """
    if not raw_html:
        return ""
    stripped = html_to_text(raw_html)
    if not stripped:
        return ""
    masked, _map = mask_text(stripped)
    return masked.strip()


def _parse_comment_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw[:10]).date()
    except (ValueError, TypeError):
        return None


def _text_hash(text: str) -> str:
    """Hash corto para detectar duplicados sin necesidad de comparar strings largos."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ── persistencia idempotente ───────────────────────────────────────────────────

def _prepare_comments(raw_comments: list[dict]) -> list[dict]:
    prepared: list[dict] = []
    for c in raw_comments:
        text_plain = sanitize_comment_text(c.get("text") or "")
        if not text_plain:
            continue
        author = (c.get("author") or "?").strip()[:200]
        cdate = _parse_comment_date(c.get("date"))
        th = _text_hash(text_plain)
        prepared.append({
            "author": author,
            "comment_date": cdate,
            "text_plain": f"{text_plain}\n[hash:{th}]",
            "hash": th,
        })
    return prepared


def _extract_hash_from_text(text: str) -> str:
    marker = text.rfind("[hash:")
    if marker == -1 or not text.endswith("]"):
        return ""
    return text[marker + 6 : -1]


def _persist_comments(
    *,
    project: str,
    items_with_prepared: list[tuple[int, list[dict]]],
) -> dict:
    """Persiste todos los comentarios preparados en UNA sola sesión.

    Con retry transitorio ante OperationalError: SQLite puede reportar
    'database is locked' brevemente cuando otros writers (p.ej. el thread
    de stacky_logger) toman el lock. Backoff exponencial corto.
    """
    if not items_with_prepared:
        return {"inserted": 0, "skipped_duplicates": 0}

    last_exc: OperationalError | None = None
    for attempt in range(1, _PERSIST_MAX_RETRIES + 1):
        try:
            return _persist_comments_attempt(
                project=project, items_with_prepared=items_with_prepared
            )
        except OperationalError as e:
            if "lock" not in str(e).lower():
                raise
            last_exc = e
            time.sleep(_PERSIST_BACKOFF_BASE * (2 ** (attempt - 1)))
    assert last_exc is not None
    raise last_exc


def _persist_comments_attempt(
    *,
    project: str,
    items_with_prepared: list[tuple[int, list[dict]]],
) -> dict:
    from db import session_scope
    from services.pm.models import PmWorkItemComment

    inserted = 0
    skipped = 0
    ado_ids = [ado_id for ado_id, _ in items_with_prepared]

    with session_scope() as session:
        existing_rows = (
            session.query(
                PmWorkItemComment.ado_id,
                PmWorkItemComment.author,
                PmWorkItemComment.text_plain,
            )
            .filter(PmWorkItemComment.ado_id.in_(ado_ids))
            .all()
        )
        existing_keys: set[tuple[int, str | None, str]] = set()
        for r_ado_id, author, text in existing_rows:
            if not text:
                continue
            existing_keys.add((int(r_ado_id), author, _extract_hash_from_text(text)))

        for ado_id, prepared in items_with_prepared:
            for p in prepared:
                key = (int(ado_id), p["author"], p["hash"])
                if key in existing_keys:
                    skipped += 1
                    continue
                row = PmWorkItemComment(
                    ado_id=int(ado_id),
                    project=project,
                    author=p["author"],
                    comment_date=p["comment_date"],
                    text_plain=p["text_plain"],
                    ai_analyzed=False,
                    sentiment_label=None,
                    sentiment_score=None,
                )
                session.add(row)
                existing_keys.add(key)
                inserted += 1

    return {"inserted": inserted, "skipped_duplicates": skipped}


def index_comments_for_work_item(
    *,
    client: AdoClient,
    ado_id: int,
    project: str,
    top: int = 50,
) -> dict:
    """Trae comentarios de un work item y los indexa con upsert por contenido."""
    try:
        raw_comments = client.fetch_comments(int(ado_id), top=top)
    except AdoApiError as e:
        logger.warning("fetch_comments(%s) falló: %s", ado_id, e)
        return {"inserted": 0, "skipped_duplicates": 0, "total_fetched": 0, "error": str(e)}

    prepared = _prepare_comments(raw_comments)
    persisted = _persist_comments(project=project, items_with_prepared=[(int(ado_id), prepared)])

    return {
        "inserted": persisted["inserted"],
        "skipped_duplicates": persisted["skipped_duplicates"],
        "total_fetched": len(raw_comments),
    }


def index_comments_bulk(
    *,
    client: AdoClient,
    project: str,
    ado_ids: list[int],
    top_per_item: int = 50,
) -> dict:
    """Indexa comentarios para una lista de work items.

    Fase 1: fetch de todos vía red (continúa ante errores individuales).
    Fase 2: persistencia en una sola transacción.
    """
    items_with_prepared: list[tuple[int, list[dict]]] = []
    total_fetched = 0
    errors: list[dict] = []

    for ado_id in ado_ids:
        try:
            raw = client.fetch_comments(int(ado_id), top=top_per_item)
        except AdoApiError as e:
            logger.warning("fetch_comments(%s) falló: %s", ado_id, e)
            errors.append({"ado_id": int(ado_id), "error": str(e)})
            continue
        total_fetched += len(raw)
        items_with_prepared.append((int(ado_id), _prepare_comments(raw)))

    persisted = _persist_comments(project=project, items_with_prepared=items_with_prepared)

    return {
        "inserted": persisted["inserted"],
        "skipped_duplicates": persisted["skipped_duplicates"],
        "total_fetched": total_fetched,
        "errors": errors,
    }
