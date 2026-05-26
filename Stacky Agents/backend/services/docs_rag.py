"""Docs RAG — Retrieval-Augmented Generation sobre documentación Markdown.

Indexa los ficheros .md de un proyecto (workspace_root/docs_subpath/**/*.md)
en una tabla SQLite `docs_index` y permite buscar chunks relevantes por
similitud TF-IDF para enriquecer el contexto de un LLM.

Uso típico:
    index_project("RSSTANDAR", "N:/SVN/RS/RSStandard/trunk")
    hits = search("RSSTANDAR", "agenda pendiente campos obligatorios", top_k=5)
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, DateTime, Float, Index, Integer, String, Text

from db import Base, session_scope

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tokenizer (igual que embeddings.py)
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"[a-záéíóúñ0-9]{3,}", re.IGNORECASE)
_STOPWORDS = {
    "the", "and", "for", "que", "con", "los", "las", "del", "una", "este",
    "esta", "como", "por", "para", "esto", "all", "any", "are", "but",
    "not", "you", "his", "her", "him", "she", "they", "their",
    "ese", "esa", "eso", "ser", "haber", "tener", "fue", "muy",
    "has", "have", "been", "will", "was", "were", "sin", "más",
}


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")
            if t.lower() not in _STOPWORDS]


def _compute_tf(text: str) -> tuple[Counter, float]:
    tokens = _tokenize(text)
    if not tokens:
        return Counter(), 0.0
    tf = Counter(tokens)
    norm = math.sqrt(sum(c * c for c in tf.values()))
    return tf, norm


# ---------------------------------------------------------------------------
# Modelo SQLAlchemy
# ---------------------------------------------------------------------------

class DocChunk(Base):
    __tablename__ = "docs_index"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_name = Column(String(80), nullable=False)
    file_path = Column(String(500), nullable=False)   # relativa a workspace_root
    section_heading = Column(Text, nullable=False, default="")
    chunk_text = Column(Text, nullable=False)
    term_freqs_json = Column(Text, nullable=False, default="{}")
    doc_norm = Column(Float, nullable=False, default=0.0)
    indexed_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_docs_project", "project_name"),
    )


# ---------------------------------------------------------------------------
# Parsing Markdown → chunks
# ---------------------------------------------------------------------------

_H2_RE = re.compile(r"^## (.+)$", re.MULTILINE)


def _split_markdown_to_chunks(
    text: str, file_path: str
) -> list[dict]:
    """Divide el contenido Markdown en chunks por secciones ## .

    Cada chunk contiene el heading (## Título) y el cuerpo de esa sección
    hasta el siguiente ## (o hasta el final del fichero).
    Si no hay secciones ##, el fichero completo es un único chunk.
    """
    matches = list(_H2_RE.finditer(text))
    chunks: list[dict] = []

    if not matches:
        # Sin headings ##: todo el fichero es un chunk
        body = text.strip()
        if body:
            chunks.append({
                "file_path": file_path,
                "section_heading": "",
                "chunk_text": body,
            })
        return chunks

    # Primer fragmento: antes del primer ##
    preamble = text[: matches[0].start()].strip()
    if preamble:
        chunks.append({
            "file_path": file_path,
            "section_heading": "",
            "chunk_text": preamble,
        })

    for i, m in enumerate(matches):
        heading = m.group(0)  # "## Título"
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        full_text = f"{heading}\n{body}" if body else heading
        if full_text.strip():
            chunks.append({
                "file_path": file_path,
                "section_heading": heading,
                "chunk_text": full_text,
            })

    return chunks


# ---------------------------------------------------------------------------
# Indexación
# ---------------------------------------------------------------------------

def index_project(
    project_name: str,
    workspace_root: str,
    docs_subpath: str = "docs",
) -> dict:
    """Indexa todos los .md bajo workspace_root/docs_subpath/ para el proyecto.

    Elimina el índice previo del proyecto antes de re-indexar.
    Retorna {"chunks_indexed": N, "files_scanned": F}.
    """
    root = Path(workspace_root) / docs_subpath
    if not root.exists():
        logger.warning("docs_rag: docs dir not found: %s", root)
        return {"chunks_indexed": 0, "files_scanned": 0, "warning": f"Directorio no encontrado: {root}"}

    md_files = sorted(root.rglob("*.md"))
    logger.info("docs_rag: indexing %d .md files for project %s", len(md_files), project_name)

    all_chunks: list[DocChunk] = []
    for md_file in md_files:
        try:
            content = md_file.read_text(encoding="utf-8-sig", errors="ignore")
        except Exception as exc:
            logger.warning("docs_rag: cannot read %s: %s", md_file, exc)
            continue

        rel_path = str(md_file.relative_to(Path(workspace_root))).replace("\\", "/")
        raw_chunks = _split_markdown_to_chunks(content, rel_path)

        for rc in raw_chunks:
            tf, norm = _compute_tf(rc["chunk_text"])
            if not tf:
                continue
            all_chunks.append(DocChunk(
                project_name=project_name,
                file_path=rc["file_path"],
                section_heading=rc["section_heading"],
                chunk_text=rc["chunk_text"],
                term_freqs_json=json.dumps(dict(tf)),
                doc_norm=norm,
                indexed_at=datetime.utcnow(),
            ))

    with session_scope() as session:
        # Eliminar índice previo del proyecto
        session.query(DocChunk).filter_by(project_name=project_name).delete()
        for chunk in all_chunks:
            session.add(chunk)

    logger.info("docs_rag: indexed %d chunks from %d files for %s",
                len(all_chunks), len(md_files), project_name)
    return {
        "chunks_indexed": len(all_chunks),
        "files_scanned": len(md_files),
    }


# ---------------------------------------------------------------------------
# IDF cache por proyecto
# ---------------------------------------------------------------------------

@dataclass
class _IdfCache:
    idf: dict[str, float]
    built_at: float


_idf_caches: dict[str, _IdfCache] = {}
_IDF_TTL = 300.0  # 5 min


def _get_idf(project_name: str, chunks: list[DocChunk]) -> dict[str, float]:
    """Calcula IDF para el corpus del proyecto (con cache de 5 min)."""
    cached = _idf_caches.get(project_name)
    if cached and (time.time() - cached.built_at) < _IDF_TTL:
        return cached.idf

    df: Counter = Counter()
    n_docs = len(chunks)
    for c in chunks:
        try:
            terms = json.loads(c.term_freqs_json or "{}")
            for t in terms:
                df[t] += 1
        except Exception:
            continue

    if n_docs == 0:
        return {}

    idf = {t: math.log((1 + n_docs) / (1 + cnt)) + 1.0 for t, cnt in df.items()}
    _idf_caches[project_name] = _IdfCache(idf=idf, built_at=time.time())
    return idf


def _invalidate_idf(project_name: str) -> None:
    _idf_caches.pop(project_name, None)


# ---------------------------------------------------------------------------
# Búsqueda
# ---------------------------------------------------------------------------

@dataclass
class DocHit:
    file_path: str
    section_heading: str
    chunk_text: str
    score: float

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "section_heading": self.section_heading,
            "chunk_text": self.chunk_text,
            "score": round(self.score, 4),
        }


def search(project_name: str, query: str, top_k: int = 5, expand_files: bool = True) -> list[DocHit]:
    """Busca chunks relevantes para la query en el índice del proyecto.

    Retorna hasta top_k resultados ordenados por score TF-IDF descendente.
    Si expand_files=True (por defecto), también devuelve todos los chunks de
    los ficheros que aparecen en los top_k, para que el LLM vea el contenido
    completo del fichero relevante aunque solo uno de sus chunks puntúe alto.
    """
    with session_scope() as session:
        chunks = session.query(DocChunk).filter_by(project_name=project_name).all()

    if not chunks:
        return []

    idf = _get_idf(project_name, chunks)
    q_tokens = _tokenize(query)
    if not q_tokens:
        return []

    # Vector de query: TF * IDF
    q_tf = Counter(q_tokens)
    q_vec: dict[str, float] = {t: q_tf[t] * idf.get(t, 1.0) for t in q_tf}
    q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0

    hits: list[DocHit] = []
    for chunk in chunks:
        try:
            tf = json.loads(chunk.term_freqs_json or "{}")
        except Exception:
            continue

        # Producto punto query · doc (con IDF ponderado)
        dot = sum(
            q_vec[t] * (tf.get(t, 0) * idf.get(t, 1.0))
            for t in q_vec
            if t in tf
        )
        if dot <= 0:
            continue

        doc_norm_idf = math.sqrt(
            sum((tf.get(t, 0) * idf.get(t, 1.0)) ** 2 for t in tf)
        ) or 1.0
        score = dot / (q_norm * doc_norm_idf)
        hits.append(DocHit(
            file_path=chunk.file_path,
            section_heading=chunk.section_heading,
            chunk_text=chunk.chunk_text,
            score=score,
        ))

    hits.sort(key=lambda h: h.score, reverse=True)
    top_hits = hits[:top_k]

    if not expand_files or not top_hits:
        return top_hits

    # Expansión de ficheros: para cada fichero en los top hits,
    # incluir TODOS los chunks de ese fichero (no solo el que puntúa más).
    matched_files = {h.file_path for h in top_hits}
    seen_ids: set[int] = set()
    expanded: list[DocHit] = []

    # Primero los top hits originales (en orden de score)
    for h in top_hits:
        expanded.append(h)

    # Luego añadir los chunks restantes de los mismos ficheros
    with session_scope() as session:
        for fp in sorted(matched_files):
            file_chunks = (
                session.query(DocChunk)
                .filter_by(project_name=project_name, file_path=fp)
                .order_by(DocChunk.id)
                .all()
            )
            for fc in file_chunks:
                # Evitar duplicados: saltar si ya está en top_hits
                already = any(
                    eh.file_path == fc.file_path and eh.section_heading == fc.section_heading
                    for eh in top_hits
                )
                if not already:
                    expanded.append(DocHit(
                        file_path=fc.file_path,
                        section_heading=fc.section_heading,
                        chunk_text=fc.chunk_text,
                        score=0.0,  # sin score propio, relevante por asociación
                    ))

    return expanded


# ---------------------------------------------------------------------------
# Estadísticas
# ---------------------------------------------------------------------------

def get_stats(project_name: str) -> dict:
    """Retorna estadísticas del índice del proyecto."""
    with session_scope() as session:
        chunks = session.query(DocChunk).filter_by(project_name=project_name).all()
        if not chunks:
            return {"chunks": 0, "files": 0, "last_indexed": None}
        files = {c.file_path for c in chunks}
        last = max((c.indexed_at for c in chunks if c.indexed_at), default=None)
        return {
            "chunks": len(chunks),
            "files": len(files),
            "last_indexed": last.isoformat() if last else None,
        }
