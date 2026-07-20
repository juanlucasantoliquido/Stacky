"""Plan 170 F1 — Store de conocimiento (flywheel).

Vista compuesta `Lesson` = línea del `lessons.jsonl` del 167 (fuente de verdad de
activas, READ-ONLY para este módulo — G10/KPI-3) + `LessonMeta` del sidecar
`lessons_meta.json` (lo ÚNICO que este módulo escribe). Matching de scope,
contadores de uso, dedup por similitud TF-IDF y sugerencias LRU/staleness.

Reglas duras (espejo 167 §4.1): `runtime_paths.data_dir()` en CADA operación (sin
cache de módulo — los tests lo monkeypatchean); lecturas tolerantes; escrituras del
sidecar bajo `_KNOWLEDGE_LOCK`; nunca se toca `lessons.jsonl`.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import runtime_paths
from services import rag_retriever

logger = logging.getLogger(__name__)

_KNOWLEDGE_LOCK = threading.Lock()
_DEDUP_SIMILARITY_THRESHOLD = 0.55
_STALE_DAYS = 60                      # C9: días sin uso para sugerir revisión
_TITLE_MAX = 80
VALID_SOURCE_KINDS = ("incident", "optimizer_lesson", "manual")

_DEFAULT_ASPECT = "knowledge_rag"
_DEFAULT_SOURCE = {"kind": "manual", "ref": None}


# --------------------------------------------------------------------------- #
# Rutas + IO tolerante
# --------------------------------------------------------------------------- #
def evolution_root() -> Path:
    return runtime_paths.data_dir() / "evolution"


def _meta_path() -> Path:
    return evolution_root() / "lessons_meta.json"


def _lessons_jsonl_path() -> Path:
    return evolution_root() / "lessons.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_active_lines() -> list[dict]:
    """Lee lessons.jsonl línea a línea (tolerante). READ-ONLY (G10). Ausente → []."""
    path = _lessons_jsonl_path()
    out: list[dict] = []
    try:
        if not path.exists():
            return []
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except Exception:  # noqa: BLE001 — línea corrupta se omite
                continue
            if isinstance(obj, dict) and obj.get("lesson_id"):
                out.append(obj)
    except Exception:  # noqa: BLE001
        return out
    return out


def read_meta() -> dict:
    """Dict completo del sidecar; tolerante → {}."""
    try:
        path = _meta_path()
        if not path.exists():
            return {}
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _write_meta(meta: dict) -> None:
    path = _meta_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Normalización
# --------------------------------------------------------------------------- #
def _norm_list(values) -> list[str]:
    out: list[str] = []
    for v in values or []:
        s = str(v).strip().casefold()
        if s and s not in out:
            out.append(s)
    return out


def _normalize_scope(scope: dict | None) -> dict:
    scope = scope or {}
    return {
        "agent_types": _norm_list(scope.get("agent_types")),
        "projects": _norm_list(scope.get("projects")),
        "tags": _norm_list(scope.get("tags")),
    }


def _normalize_title(s: str) -> str:
    return " ".join((s or "").casefold().split())


def _default_title(text: str) -> str:
    first = (text or "").splitlines()[0] if (text or "").strip() else ""
    return first[:_TITLE_MAX]


# --------------------------------------------------------------------------- #
# Meta CRUD (bajo lock)
# --------------------------------------------------------------------------- #
def _new_meta_entry(lesson_id: str, *, title: str, scope: dict | None,
                    source: dict | None, eval_case_id) -> dict:
    now = _now_iso()
    return {
        "lesson_id": lesson_id,
        "title": title,
        "scope": _normalize_scope(scope),
        "source": _normalize_source(source),
        "eval_case_id": eval_case_id,
        "usage_count": 0,
        "last_injected_at": None,
        "created_at": now,
        "updated_at": now,
    }


def _normalize_source(source: dict | None) -> dict:
    if not source:
        return dict(_DEFAULT_SOURCE)
    kind = source.get("kind")
    if kind not in VALID_SOURCE_KINDS:
        raise ValueError("invalid_meta:source")
    return {"kind": kind, "ref": source.get("ref")}


def upsert_meta(lesson_id: str, *, title: str, scope: dict | None = None,
                source: dict | None = None, eval_case_id=None) -> dict:
    """Crea/actualiza la entrada §4.2. Preserva usage_count/last_injected_at/
    created_at existentes. ValueError('invalid_meta:<campo>') si falla."""
    if not lesson_id or not str(lesson_id).strip():
        raise ValueError("invalid_meta:lesson_id")
    if title is None or not str(title).strip():
        raise ValueError("invalid_meta:title")
    norm_source = _normalize_source(source)
    with _KNOWLEDGE_LOCK:
        meta = read_meta()
        existing = meta.get(lesson_id)
        if existing:
            existing["title"] = str(title)
            if scope is not None:
                existing["scope"] = _normalize_scope(scope)
            existing["source"] = norm_source
            if eval_case_id is not None:
                existing["eval_case_id"] = eval_case_id
            existing["updated_at"] = _now_iso()
            meta[lesson_id] = existing
            entry = existing
        else:
            entry = _new_meta_entry(lesson_id, title=str(title), scope=scope,
                                    source=source, eval_case_id=eval_case_id)
            meta[lesson_id] = entry
        _write_meta(meta)
        return dict(entry)


def patch_meta(lesson_id: str, **patch) -> dict:
    """SOLO {'title','scope'}. Otra clave → ValueError('invalid_meta:campo_no_editable').
    KeyError('lesson_not_found') si no hay meta NI línea activa (legacy → crea meta)."""
    for key in patch:
        if key not in ("title", "scope"):
            raise ValueError("invalid_meta:campo_no_editable")
    with _KNOWLEDGE_LOCK:
        meta = read_meta()
        entry = meta.get(lesson_id)
        if entry is None:
            active = {ln.get("lesson_id"): ln for ln in _read_active_lines()}
            line = active.get(lesson_id)
            if line is None:
                raise KeyError("lesson_not_found")
            entry = _new_meta_entry(
                lesson_id, title=_default_title(line.get("text") or ""),
                scope=None, source=None, eval_case_id=None,
            )
        if "title" in patch:
            t = patch["title"]
            if t is None or not str(t).strip():
                raise ValueError("invalid_meta:title")
            entry["title"] = str(t)
        if "scope" in patch:
            entry["scope"] = _normalize_scope(patch["scope"])
        entry["updated_at"] = _now_iso()
        meta[lesson_id] = entry
        _write_meta(meta)
        return dict(entry)


# --------------------------------------------------------------------------- #
# Vista compuesta
# --------------------------------------------------------------------------- #
def _compose_active(line: dict, meta_entry: dict | None) -> dict:
    lesson_id = line.get("lesson_id")
    text = line.get("text") or ""
    if meta_entry:
        title = meta_entry.get("title") or _default_title(text)
        scope = _normalize_scope(meta_entry.get("scope"))
        source = meta_entry.get("source") or dict(_DEFAULT_SOURCE)
        eval_case_id = meta_entry.get("eval_case_id")
        usage_count = int(meta_entry.get("usage_count") or 0)
        last_injected_at = meta_entry.get("last_injected_at")
    else:
        title = _default_title(text)
        scope = {"agent_types": [], "projects": [], "tags": []}
        source = dict(_DEFAULT_SOURCE)
        eval_case_id = None
        usage_count = 0
        last_injected_at = None
    return {
        "lesson_id": lesson_id,
        "aspect_id": line.get("aspect_id") or _DEFAULT_ASPECT,
        "text": text,
        "origin": line.get("origin") or "manual",
        "created_at": line.get("created_at"),
        "active": True,
        "title": title,
        "scope": scope,
        "source": source,
        "eval_case_id": eval_case_id,
        "usage_count": usage_count,
        "last_injected_at": last_injected_at,
    }


def _compose_retired(meta_entry: dict) -> dict:
    return {
        "lesson_id": meta_entry.get("lesson_id"),
        "aspect_id": _DEFAULT_ASPECT,
        "text": "",
        "origin": (meta_entry.get("source") or {}).get("kind") or "manual",
        "created_at": meta_entry.get("created_at"),
        "active": False,
        "title": meta_entry.get("title") or "",
        "scope": _normalize_scope(meta_entry.get("scope")),
        "source": meta_entry.get("source") or dict(_DEFAULT_SOURCE),
        "eval_case_id": meta_entry.get("eval_case_id"),
        "usage_count": int(meta_entry.get("usage_count") or 0),
        "last_injected_at": meta_entry.get("last_injected_at"),
    }


def list_lessons(include_retired: bool = False) -> list[dict]:
    lines = _read_active_lines()
    meta = read_meta()
    active_ids = set()
    active_views: list[dict] = []
    for line in lines:
        lid = line.get("lesson_id")
        if lid in active_ids:
            continue
        active_ids.add(lid)
        active_views.append(_compose_active(line, meta.get(lid)))
    active_views.sort(key=lambda l: l.get("created_at") or "", reverse=True)
    if not include_retired:
        return active_views
    retired = [
        _compose_retired(entry)
        for lid, entry in meta.items()
        if lid not in active_ids
    ]
    retired.sort(key=lambda l: l.get("created_at") or "", reverse=True)
    return active_views + retired


def get_lesson(lesson_id: str) -> dict | None:
    for l in list_lessons(include_retired=True):
        if l["lesson_id"] == lesson_id:
            return l
    return None


# --------------------------------------------------------------------------- #
# Matching + ranking (funciones puras)
# --------------------------------------------------------------------------- #
def _axis_ok(value: str | None, allowed: list[str]) -> bool:
    if not allowed:            # lista vacía = global
        return True
    if value is None:
        return False
    v = value.casefold()
    return any(v == str(a).casefold() for a in allowed)


def lesson_matches(scope: dict, *, agent_type: str | None,
                   project_name: str | None) -> bool:
    scope = scope or {}
    agent_ok = _axis_ok(agent_type, scope.get("agent_types") or [])
    project_ok = _axis_ok(project_name, scope.get("projects") or [])
    return agent_ok and project_ok


def active_lessons_for(agent_type: str | None,
                       project_name: str | None) -> list[dict]:
    out = [
        l for l in list_lessons(include_retired=False)
        if lesson_matches(l.get("scope") or {}, agent_type=agent_type,
                          project_name=project_name)
    ]
    out.sort(key=lambda l: l.get("created_at") or "", reverse=True)
    return out


def rank_lessons(lessons: list[dict], query: str | None, top_n: int) -> list[dict]:
    if not lessons:
        return []
    top_n = max(1, int(top_n))
    if query and query.strip():
        try:
            chunks = [
                rag_retriever.RagChunk(
                    id=str(l.get("lesson_id")),
                    text=f"{l.get('title') or ''}\n{l.get('text') or ''}",
                    payload=l,
                )
                for l in lessons
            ]
            index = rag_retriever.build_index(chunks)
            hits = rag_retriever.retrieve(index, query, top_k=top_n)
            ranked = [chunk.payload for chunk, score in hits if score > 0.0]
            if ranked:
                chosen = {l.get("lesson_id") for l in ranked}
                rest = sorted(
                    [l for l in lessons if l.get("lesson_id") not in chosen],
                    key=lambda l: l.get("created_at") or "", reverse=True,
                )
                return (ranked + rest)[:top_n]
        except Exception:  # noqa: BLE001 — nunca lanza (contrato rag_retriever)
            pass
    return sorted(
        lessons, key=lambda l: l.get("created_at") or "", reverse=True
    )[:top_n]


# --------------------------------------------------------------------------- #
# Armado del bloque de contexto (§4.5) — PURO, único armador
# --------------------------------------------------------------------------- #
_BLOCK_HEADER = (
    "LECCIONES APRENDIDAS DE INCIDENCIAS RESUELTAS Y MEJORAS VERIFICADAS "
    "(aplicalas cuando toquen tu tarea; no las transcribas en el output; si dos "
    "lecciones se contradicen, priorizá la de número más bajo y anotá el "
    "conflicto en tu resumen):"
)


def build_lessons_block(lessons: list[dict], *, query: str | None,
                        top_n: int, max_chars: int) -> dict | None:
    """§4.5 — PURA. rank + header + entradas numeradas + cap duro. None si vacío.
    NO toca contadores, NO lee flags (los límites llegan por parámetro)."""
    if not lessons:
        return None
    selected = rank_lessons(lessons, query, top_n)
    if not selected:
        return None
    content = _BLOCK_HEADER
    used_ids: list[str] = []
    truncated = False
    for idx, lesson in enumerate(selected, start=1):
        title = lesson.get("title") or _default_title(lesson.get("text") or "")
        text = lesson.get("text") or ""
        entry = f"\n{idx}. [{title}] {text}"
        if len(content) + len(entry) <= max_chars:
            content += entry
            used_ids.append(lesson.get("lesson_id"))
        else:
            if not used_ids:
                # primera entrada sola excede el cap → truncar a max_chars con "…"
                room = max(0, max_chars - len(content) - 1)
                content = content + entry[:room] + "…"
                used_ids.append(lesson.get("lesson_id"))
            truncated = True
            break
    return {
        "kind": "text",
        "id": "evolution-lessons",
        "title": f"Lecciones aprendidas (Stacky) — {len(used_ids)}",
        "content": content,
        "metadata": {"lesson_ids": used_ids, "truncated": truncated},
    }


# --------------------------------------------------------------------------- #
# Contadores de uso (§4.2 C3 — "seleccionada para inyección")
# --------------------------------------------------------------------------- #
def record_injection(lesson_ids: list[str]) -> None:
    """usage_count += 1 y last_injected_at = ahora para cada id. id sin meta → la
    crea con defaults §4.2. Best-effort: cualquier excepción → warning, no rompe."""
    try:
        if not lesson_ids:
            return
        active = {ln.get("lesson_id"): ln for ln in _read_active_lines()}
        with _KNOWLEDGE_LOCK:
            meta = read_meta()
            now = _now_iso()
            for lid in lesson_ids:
                entry = meta.get(lid)
                if entry is None:
                    line = active.get(lid)
                    title = _default_title((line or {}).get("text") or "") or str(lid)
                    entry = _new_meta_entry(lid, title=title or str(lid), scope=None,
                                            source=None, eval_case_id=None)
                entry["usage_count"] = int(entry.get("usage_count") or 0) + 1
                entry["last_injected_at"] = now
                entry["updated_at"] = now
                meta[lid] = entry
            _write_meta(meta)
    except Exception as exc:  # noqa: BLE001 — camino caliente, jamás rompe un run
        logger.warning("record_injection no pudo persistir (continuando): %s", exc)


# --------------------------------------------------------------------------- #
# Dedup en la cosecha (§4.9)
# --------------------------------------------------------------------------- #
def find_similar(candidate_title: str, candidate_body: str) -> list[dict]:
    actives = list_lessons(include_retired=False)
    if not actives:
        return []
    scores: dict[str, dict] = {}
    cand_norm = _normalize_title(candidate_title)
    # 1) match exacto de título normalizado
    for l in actives:
        if _normalize_title(l.get("title") or "") == cand_norm and cand_norm:
            scores[l["lesson_id"]] = {
                "lesson_id": l["lesson_id"], "title": l.get("title") or "",
                "score": 1.0,
            }
    # 2) TF-IDF
    try:
        chunks = [
            rag_retriever.RagChunk(
                id=str(l["lesson_id"]),
                text=f"{l.get('title') or ''}\n{l.get('text') or ''}",
                payload=l,
            )
            for l in actives
        ]
        index = rag_retriever.build_index(chunks)
        query = f"{candidate_title}\n{candidate_body}"
        for chunk, score in rag_retriever.retrieve(index, query, top_k=3):
            if score >= _DEDUP_SIMILARITY_THRESHOLD:
                lid = chunk.payload["lesson_id"]
                prev = scores.get(lid)
                if prev is None or score > prev["score"]:
                    scores[lid] = {
                        "lesson_id": lid,
                        "title": chunk.payload.get("title") or "",
                        "score": float(score),
                    }
    except Exception:  # noqa: BLE001
        pass
    return sorted(scores.values(), key=lambda d: d["score"], reverse=True)


# --------------------------------------------------------------------------- #
# Cosecha ya realizada (§4.4 C2)
# --------------------------------------------------------------------------- #
def _harvested_suffixes(prefix: str) -> set[str]:
    from services import evolution_store
    out: set[str] = set()
    try:
        for p in evolution_store.list_proposals(aspect_id="knowledge_rag"):
            if p.get("status") == "rejected":
                continue
            evidence = p.get("evidence") or []
            if not any(isinstance(x, str) and x.startswith("harvest:") for x in evidence):
                continue
            for e in evidence:
                if isinstance(e, str) and e.startswith(prefix):
                    out.add(e.split(":", 1)[1])
    except Exception:  # noqa: BLE001
        return out
    return out


def harvested_incident_ids() -> set[str]:
    return _harvested_suffixes("incident:")


def harvested_optimizer_lesson_ids() -> set[str]:
    return _harvested_suffixes("optimizer_lesson:")


# --------------------------------------------------------------------------- #
# Sugerencias de retiro (§4.10 C9) — SIEMPRE sugerencia, jamás auto-borrado
# --------------------------------------------------------------------------- #
def _max_lessons() -> int:
    from config import config as _cfg
    try:
        return int(getattr(_cfg, "STACKY_KNOWLEDGE_MAX_LESSONS", 200))
    except Exception:  # noqa: BLE001
        return 200


def _parse_iso(value) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except Exception:  # noqa: BLE001
        return None


def retire_suggestions() -> list[dict]:
    actives = list_lessons(include_retired=False)
    cap = _max_lessons()
    by_id: dict[str, dict] = {}

    def _row(l: dict, reason: str) -> dict:
        return {
            "lesson_id": l["lesson_id"], "title": l.get("title") or "",
            "usage_count": int(l.get("usage_count") or 0),
            "created_at": l.get("created_at"), "reason": reason,
        }

    # Regla 1 (LRU) — solo si activas > cap
    if len(actives) > cap:
        ordered = sorted(
            actives,
            key=lambda l: (int(l.get("usage_count") or 0), l.get("created_at") or ""),
        )
        for l in ordered[: len(actives) - cap]:
            by_id[l["lesson_id"]] = _row(l, "lru_por_uso")

    # Regla 2 (staleness) — SIEMPRE, usage_count == 0 y edad > _STALE_DAYS
    cutoff = datetime.now(timezone.utc) - timedelta(days=_STALE_DAYS)
    for l in actives:
        if l["lesson_id"] in by_id:
            continue                      # precedencia regla 1
        if int(l.get("usage_count") or 0) != 0:
            continue
        created = _parse_iso(l.get("created_at"))
        if created is not None and created < cutoff:
            by_id[l["lesson_id"]] = _row(l, "sin_uso_prolongado")

    return sorted(
        by_id.values(),
        key=lambda d: (int(d.get("usage_count") or 0), d.get("created_at") or ""),
    )
