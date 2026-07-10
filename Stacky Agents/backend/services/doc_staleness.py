"""services/doc_staleness.py — Plan 114 · Doctor de staleness doc↔código.

Para cada arista `code_ref` (nota → archivo de código) del grafo (plan 109),
compara la fecha del último commit git del archivo de código contra la de la nota.
Si el código es más nuevo, marca la arista como `stale` y la nota con `has_stale`.

Señal 100% git (objetiva), sin LLM. Determinístico. NUNCA lanza: si git no está o
falla, degrada a "sin staleness" (stale=False). Ver plan 114 §4-§5.
"""
from __future__ import annotations

import posixpath
import subprocess
import time

_MAX_GIT_LOOKUPS = 500       # (C3) tope duro de consultas git por anotación
_EPOCH_TTL_SECONDS = 60      # (C3) cache de epochs entre requests (mismo TTL que el grafo 109)
# cache módulo: (repo_root, rel_path) -> (cached_at_monotonic, epoch | None)
_epoch_cache: dict[tuple[str, str], tuple[float, int | None]] = {}


def git_last_commit_epoch(repo_root: str, rel_path: str) -> int | None:
    """Epoch (int) del último commit que tocó rel_path, o None si no es git / no existe / error.

    Comando: git -C <repo_root> log -1 --format=%ct -- <rel_path>. Timeout 5 s.
    (C3) Cachea el resultado _EPOCH_TTL_SECONDS por (repo_root, rel_path).
    """
    key = (repo_root, rel_path)
    hit = _epoch_cache.get(key)
    if hit and time.monotonic() - hit[0] < _EPOCH_TTL_SECONDS:
        return hit[1]
    try:
        out = subprocess.run(
            ["git", "-C", repo_root, "log", "-1", "--format=%ct", "--", rel_path],
            capture_output=True, text=True, timeout=5)
        s = (out.stdout or "").strip()
        epoch = int(s) if s.isdigit() else None
    except Exception:
        epoch = None
    _epoch_cache[key] = (time.monotonic(), epoch)
    return epoch


def _note_repo_path(node: dict, sources_by_id: dict[str, dict]) -> str | None:
    """(C2) Path de la nota RELATIVO AL REPO: node.path es relativo a su FUENTE,
    hay que anteponer source.relative_path (de graph['sources']).
    relative_path == '.' → node.path directo. Fuente desconocida → None."""
    src = sources_by_id.get(node.get("source_id", ""))
    if not src:
        return None
    rel = str(src.get("relative_path") or ".")
    p = node["path"] if rel in (".", "") else posixpath.join(rel, node["path"])
    return posixpath.normpath(p)


def annotate_staleness(graph: dict, repo_root: str) -> dict:
    """Agrega 'stale' SOLO a aristas code_ref (C4) y 'has_stale' a nodos nota,
    más 'stale_stats' [ADICIÓN ARQUITECTO]. Determinístico. NUNCA lanza.
    Regla: arista (nota -> code) es stale si epoch_git(code) > epoch_git(nota),
    ambos no-None. (C5) La señal es SOLO git: el 'updated' de frontmatter queda
    fuera de scope. Si falta cualquiera de los dos epochs -> stale=False.
    IMPORTANTE (C1): el CALLER pasa una COPIA del grafo (deepcopy en el wiring);
    esta función asume que puede mutar su argumento."""
    lookups = 0

    def ep(rel):
        nonlocal lookups
        if lookups >= _MAX_GIT_LOOKUPS:   # (C3) excedente: no se puede afirmar nada
            return None
        lookups += 1
        return git_last_commit_epoch(repo_root, rel)

    sources_by_id = {s["id"]: s for s in graph.get("sources", [])}
    notes_by_id = {n["id"]: n for n in graph.get("nodes", []) if n.get("kind") == "note"}
    note_epoch: dict[str, int | None] = {}
    stale_notes: set[str] = set()
    stale_edges = 0
    for e in graph.get("edges", []):
        if e.get("kind") != "code_ref":
            continue                       # (C4) las demás aristas NO ganan el campo
        note_id, code_id = e["source"], e["target"]
        code_path = code_id[len("code:"):] if str(code_id).startswith("code:") else None  # (C6)
        ce = ep(code_path) if code_path else None
        if note_id not in note_epoch:
            node = notes_by_id.get(note_id)
            npath = _note_repo_path(node, sources_by_id) if node else None
            note_epoch[note_id] = ep(npath) if npath else None
        ne = note_epoch[note_id]
        e["stale"] = bool(ce is not None and ne is not None and ce > ne)
        if e["stale"]:
            stale_notes.add(note_id)
            stale_edges += 1
    for n in graph.get("nodes", []):
        if n.get("kind") == "note":
            n["has_stale"] = n["id"] in stale_notes
    graph["stale_stats"] = {"stale_edges": stale_edges, "stale_notes": len(stale_notes)}  # [ADICIÓN ARQUITECTO]
    return graph
