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
from services import lexical_core  # Plan 115 — núcleo léxico TF-IDF compartido

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


# Plan 115 — política de tokenización que REPLICA _TOKEN_RE + _STOPWORDS (min 3, ignorecase).
_TOKENIZE_OPTS = lexical_core.TokenizeOptions(
    pattern=r"[a-záéíóúñ0-9]{3,}", ignorecase=True,
    lowercase_token=True, stopwords=frozenset(_STOPWORDS),
)


def _tokenize(text: str) -> list[str]:
    return lexical_core.tokenize(text, _TOKENIZE_OPTS)


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

    n_docs = len(chunks)
    if n_docs == 0:
        return {}

    # (C2) La cache _idf_caches y su TTL quedan intactos; solo el CÁLCULO del IDF
    # pasa a lexical_core. Se preserva n_docs=len(chunks): un chunk cuyo JSON no
    # parsea aporta un set vacío (no suma df, pero cuenta en n) — mismo resultado.
    token_sets: list[set] = []
    for c in chunks:
        try:
            token_sets.append(set(json.loads(c.term_freqs_json or "{}")))
        except Exception:
            token_sets.append(set())

    idf = lexical_core.inverse_doc_frequencies(token_sets)
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

    # Vector de query: TF crudo (Counter) — el coseno IDF-ponderado vive en lexical_core.
    q_tf = Counter(q_tokens)

    hits: list[DocHit] = []
    for chunk in chunks:
        try:
            tf = json.loads(chunk.term_freqs_json or "{}")
        except Exception:
            continue

        # (Plan 115) Coseno TF-IDF idéntico al anterior; el filtro dot<=0 equivale
        # a score<=0 (norms>0 ⇒ mismo signo que el producto punto).
        score = lexical_core.cosine_tfidf(q_tf, tf, idf)
        if score <= 0:
            continue

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
# Plan 112 — Telemetría A/B del retrieval híbrido (en memoria, señal de sesión)
# ---------------------------------------------------------------------------

_hybrid_telemetry = {"queries": 0, "queries_with_new": 0,
                     "hits_lexical": 0, "hits_added": 0}


def record_hybrid_query(lexical: int, added: int, new_from_expansion: bool) -> None:
    _hybrid_telemetry["queries"] += 1
    _hybrid_telemetry["hits_lexical"] += int(lexical)
    _hybrid_telemetry["hits_added"] += int(added)
    if new_from_expansion:
        _hybrid_telemetry["queries_with_new"] += 1


def _reset_hybrid_telemetry() -> None:  # para tests
    for k in _hybrid_telemetry:
        _hybrid_telemetry[k] = 0


def get_hybrid_telemetry() -> dict:
    return dict(_hybrid_telemetry)


# ---------------------------------------------------------------------------
# Plan 112 — Retrieval híbrido: puente grafo↔docs_rag (backlinks + vecindad)
# ---------------------------------------------------------------------------

def _basename_lower(path: str) -> str:
    return path.replace("\\", "/").rsplit("/", 1)[-1].lower()


def _build_backlink_index(project_name: str) -> tuple[dict[str, int], dict[str, list[str]]]:
    """Devuelve (backlinks_by_path, neighbors_by_path) para las notas de PROYECTO.

    - backlinks_by_path[file_path] = in_degree del nodo nota correspondiente.
    - neighbors_by_path[file_path] = file_paths de notas a 1 arista (out o in), dedup.

    Si el grafo no está disponible o la flag 109 está OFF, devuelve ({}, {}):
    el híbrido degrada a léxico puro sin romper. (Plan 112 F1, fallback basename C2.)
    """
    try:
        from services import doc_graph
        from config import config
        if not getattr(config, "STACKY_DOCS_GRAPH_ENABLED", False):
            return {}, {}
        graph = doc_graph.build_graph(project_name=project_name)
    except Exception as exc:
        logger.warning("docs_rag: hybrid backlink index unavailable: %s", exc)
        return {}, {}

    # nodo nota project-docs -> file_path estilo docs_rag (path relativo a la fuente)
    id_to_path: dict[str, str] = {}
    backlinks: dict[str, int] = {}
    for n in graph.get("nodes", []):
        if n.get("kind") != "note" or not str(n.get("source_id", "")).startswith("project-docs"):
            continue
        p = str(n["path"]).replace("\\", "/")
        id_to_path[n["id"]] = p
        backlinks[p] = int(n.get("in_degree", 0))

    # Vecindad no dirigida (1-hop en cualquier sentido) entre nodos nota resueltos.
    neighbors: dict[str, list[str]] = {}
    for e in graph.get("edges", []):
        s, t = e.get("source"), e.get("target")
        sp, tp = id_to_path.get(s), id_to_path.get(t)
        if sp and tp:
            neighbors.setdefault(sp, []).append(tp)
            neighbors.setdefault(tp, []).append(sp)
    for k in list(neighbors):
        seen: set[str] = set()
        out: list[str] = []
        for v in neighbors[k]:
            if v not in seen and v != k:
                seen.add(v)
                out.append(v)
        neighbors[k] = out

    # (C2) Fallback por basename para chunk_paths cuyo file_path no matchea exacto
    # con ningún node.path. Se construye un índice basename->node_path OMITIENDO
    # los basenames ambiguos (repetidos); el chunk_path resuelto hereda backlinks y
    # vecindad del nodo (alias). Sin match ni por basename → 0 backlinks, sin vecinos.
    chunk_paths = _distinct_chunk_paths(project_name)
    non_exact = [cp for cp in chunk_paths if cp not in backlinks]
    if non_exact:
        base_counts: Counter = Counter(_basename_lower(np) for np in backlinks)
        base_index = {
            _basename_lower(np): np
            for np in backlinks
            if base_counts[_basename_lower(np)] == 1
        }
        for cp in non_exact:
            node_path = base_index.get(_basename_lower(cp))
            if node_path is None:
                continue
            backlinks[cp] = backlinks[node_path]
            if node_path in neighbors:
                neighbors[cp] = list(neighbors[node_path])

    return backlinks, neighbors


def _distinct_chunk_paths(project_name: str) -> list[str]:
    """file_paths distintos presentes en la tabla DocChunk del proyecto."""
    with session_scope() as session:
        rows = (session.query(DocChunk.file_path)
                .filter_by(project_name=project_name)
                .distinct().all())
    return [r[0] for r in rows]


def _read_hybrid_weights() -> tuple[float, float, int]:
    from config import config

    def _clamp(v, lo, hi):
        return max(lo, min(hi, v))

    alpha = _clamp(float(getattr(config, "STACKY_DOCS_RAG_HYBRID_ALPHA", 1.0)), 0.0, 10.0)
    beta = _clamp(float(getattr(config, "STACKY_DOCS_RAG_HYBRID_BETA", 0.15)), 0.0, 10.0)
    maxn = int(_clamp(int(getattr(config, "STACKY_DOCS_RAG_HYBRID_MAX_NEIGHBORS", 8)), 0, 100))
    return alpha, beta, maxn


_HYBRID_RESULT_CAP_FACTOR = 3  # (C1) tope duro: len(resultado) <= top_k * 3


def _rerank_with_backlinks(hits: list[DocHit], backlinks: dict[str, int],
                           alpha: float, beta: float) -> list[DocHit]:
    """Reordena por clave = alpha*score + beta*log(1+backlinks(file)).

    (C4) NO muta los DocHit ni crea copias: la clave combinada es SOLO para
    ordenar; los scores visibles siguen siendo los léxicos originales. `sorted`
    es estable → empates conservan el orden relativo previo.
    """
    def _key(h: DocHit) -> float:
        bl = backlinks.get(h.file_path, 0)
        return alpha * h.score + beta * math.log1p(bl)

    return sorted(hits, key=_key, reverse=True)


def search_hybrid(project_name: str, query: str, top_k: int = 5,
                  expand_files: bool = True, *, collect_debug: bool = False):
    """Retrieval híbrido: léxico (search) + expansión 1-hop por grafo + prior backlinks.

    Contrato: si no hay grafo (flag 109 OFF o error) degrada EXACTAMENTE a search().
    Con collect_debug=True devuelve (hits, debug_dict) para el bloque de diagnóstico
    opt-in de la ruta (plan 112 F3, adición arquitecto); si no, devuelve list[DocHit].
    """
    alpha, beta, max_neighbors = _read_hybrid_weights()
    base_hits = search(project_name, query, top_k=top_k, expand_files=expand_files)
    backlinks, neighbors = _build_backlink_index(project_name)

    def _debug(lexical_files, expanded_files):
        return {
            "lexical_files": lexical_files,
            "expanded_files": expanded_files,
            "weights": {"alpha": alpha, "beta": beta, "max_neighbors": max_neighbors},
        }

    if not neighbors and not backlinks:
        record_hybrid_query(lexical=len(base_hits), added=0, new_from_expansion=False)
        lex_files = []
        for h in base_hits:
            if h.file_path not in lex_files:
                lex_files.append(h.file_path)
        if collect_debug:
            return base_hits, _debug(lex_files, [])
        return base_hits  # degradación a léxico puro

    # 1-hop: por cada file_path de los top hits léxicos, traer chunks de vecinos.
    lexical_files: list[str] = []
    for h in base_hits:
        if h.file_path not in lexical_files:
            lexical_files.append(h.file_path)
    neighbor_files: list[str] = []
    for fp in lexical_files:
        for nb in neighbors.get(fp, [])[:max_neighbors]:
            if nb not in lexical_files and nb not in neighbor_files:
                neighbor_files.append(nb)

    added: list[DocHit] = []
    if neighbor_files:
        with session_scope() as session:
            for nb in neighbor_files:
                for fc in (session.query(DocChunk)
                           .filter_by(project_name=project_name, file_path=nb)
                           .order_by(DocChunk.id).all()):
                    added.append(DocHit(file_path=fc.file_path,
                                        section_heading=fc.section_heading,
                                        chunk_text=fc.chunk_text,
                                        score=0.0))  # relevante por vecindad, sin score léxico

    combined = base_hits + added
    reranked = _rerank_with_backlinks(combined, backlinks, alpha, beta)
    reranked = reranked[: max(1, top_k) * _HYBRID_RESULT_CAP_FACTOR]  # (C1) tope duro
    record_hybrid_query(lexical=len(base_hits), added=len(added),
                        new_from_expansion=bool(added))
    if collect_debug:
        return reranked, _debug(lexical_files, neighbor_files)
    return reranked


# ---------------------------------------------------------------------------
# Estadísticas
# ---------------------------------------------------------------------------

def get_stats(project_name: str) -> dict:
    """Retorna estadísticas del índice del proyecto."""
    with session_scope() as session:
        chunks = session.query(DocChunk).filter_by(project_name=project_name).all()
        if not chunks:
            return {"chunks": 0, "files": 0, "last_indexed": None,
                    "hybrid": get_hybrid_telemetry()}
        files = {c.file_path for c in chunks}
        last = max((c.indexed_at for c in chunks if c.indexed_at), default=None)
        return {
            "chunks": len(chunks),
            "files": len(files),
            "last_indexed": last.isoformat() if last else None,
            "hybrid": get_hybrid_telemetry(),  # Plan 112 F4 — señal A/B aditiva
        }
