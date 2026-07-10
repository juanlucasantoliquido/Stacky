"""Plan 113 — Documentador agéntico 1-click polifuncional.

Orquesta un pipeline que: (1) detecta el estado de la doc vía doc_health (plan
109); (2) decide modos (RECONSTRUIR/NORMALIZAR/COMPLETAR/ACTUALIZAR/ENRIQUECER);
(3) invoca al agente 'Documentador' por modo; (4) escribe las propuestas a una
rama git dedicada y revertible, protegiendo docs/sistema/. El agente propone;
el aplicador determinista escribe. Nunca push, nunca merge automático, nunca stash.
"""
from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)

# Persona de fallback (los .agent.md están gitignoreados; patrón plan 112 F5).
_DEFAULT_DOCUMENTADOR_PROMPT = (
    "Sos un documentador técnico anti-alucinación. Producís documentación en "
    "formato Obsidian (frontmatter YAML + wikilinks [[nota]]). Reglas duras:\n"
    "1. TODA afirmación nueva lleva una marca de confianza: [V] (verificado contra "
    "el código, con archivo:línea), [INF] (inferido) o [NV] (no verificable).\n"
    "2. Las [V] SIEMPRE citan archivo:línea real del contexto provisto. Si algo no "
    "está en el contexto, no lo inventás: lo marcás [NV] o lo omitís.\n"
    "3. NUNCA tocás ni dupliques docs/sistema/ (documentación canónica read-only): "
    "solo la linkeás.\n"
    "4. Respondés SOLO bloques delimitados, uno por archivo, con este formato exacto:\n"
    '   <<<DOC path="ruta/relativa.md" action="create|patch" sources="a.py:10,b.ts:3">>>\n'
    "   ---\n"
    "   title: ...\n"
    "   ---\n"
    "   # Título\n"
    "   Contenido markdown con marcas y wikilinks.\n"
    "   <<<END>>>\n"
    "   Sin prosa fuera de los bloques. Español, conciso, accionable."
)


# ---------------------------------------------------------------------------
# F1 — Selector de modos determinista
# ---------------------------------------------------------------------------

class DocumenterMode(str, Enum):
    RECONSTRUIR = "RECONSTRUIR"
    NORMALIZAR = "NORMALIZAR"
    COMPLETAR = "COMPLETAR"
    ACTUALIZAR = "ACTUALIZAR"
    ENRIQUECER = "ENRIQUECER"


@dataclass
class DocumenterPlan:
    status: str                      # doc_health.status
    modes: list[DocumenterMode]
    uncovered_modules: list[str] = field(default_factory=list)
    notes_to_normalize: list[str] = field(default_factory=list)  # file_paths sin frontmatter
    reason: str = ""


def plan_documenter_run(project_name: str) -> DocumenterPlan:
    """Devuelve el plan de modos (determinista, sin LLM) según doc_health (plan 109)."""
    from services import doc_graph
    graph = doc_graph.build_graph(project_name=project_name)
    health = graph.get("doc_health") or {"status": "SIN_DOCS"}
    st = health.get("status", "SIN_DOCS")

    if st == "SIN_DOCS":
        return DocumenterPlan(
            st, [DocumenterMode.RECONSTRUIR, DocumenterMode.ENRIQUECER],
            reason="El proyecto no tiene notas; se reconstruye desde el código.")
    if st == "FORMATO_NO_OBSIDIAN":
        no_fm = [
            n["path"] for n in graph.get("nodes", [])
            if n.get("kind") == "note"
            and str(n.get("source_id", "")).startswith("project-docs")
            and not n.get("has_frontmatter")
        ]
        return DocumenterPlan(
            st, [DocumenterMode.NORMALIZAR, DocumenterMode.ENRIQUECER],
            notes_to_normalize=no_fm, reason="Notas sin frontmatter ni wikilinks.")
    if st == "INCOMPLETA":
        return DocumenterPlan(
            st, [DocumenterMode.COMPLETAR, DocumenterMode.ENRIQUECER],
            uncovered_modules=list(health.get("uncovered_modules", [])),
            reason="Módulos de código sin nota.")
    # SANA (o cualquier otro): solo enriquecer links.
    return DocumenterPlan(
        st, [DocumenterMode.ENRIQUECER], reason="Doc sana; solo enriquecer links.")


# ---------------------------------------------------------------------------
# F2 — Contexto por modo + invocación del agente + parseo del artefacto
# ---------------------------------------------------------------------------

@dataclass
class DocProposal:
    path: str
    action: str            # "create" | "patch"
    content: str
    marks_ok: bool
    sources: list[str] = field(default_factory=list)


_MARKS = ("[V]", "[INF]", "[NV]")
_PROPOSAL_RE = re.compile(
    r'<<<DOC\s+path="(?P<path>[^"]*)"\s+action="(?P<action>[^"]*)"\s+'
    r'sources="(?P<sources>[^"]*)"\s*>>>(?P<body>.*?)<<<END>>>',
    re.DOTALL,
)
_INVOKE_TIMEOUT_S = 1800  # anti-zombie, mismo default que el CLI


def parse_proposals(raw: str) -> list[DocProposal]:
    """Parsea la salida del agente (formato determinista) a DocProposal.

    Bloques malformados o con action inválida se descartan con log (nunca crashea).
    marks_ok=True solo si el cuerpo contiene al menos una marca [V]/[INF]/[NV].
    """
    out: list[DocProposal] = []
    for m in _PROPOSAL_RE.finditer(raw or ""):
        path = m.group("path").strip()
        action = m.group("action").strip().lower()
        body = m.group("body").strip("\n")
        if not path or action not in ("create", "patch"):
            logger.warning("doc_documenter: proposal descartada (path/action inválido): %r/%r",
                           path, action)
            continue
        sources = [s.strip() for s in m.group("sources").split(",") if s.strip()]
        marks_ok = any(tok in body for tok in _MARKS)
        out.append(DocProposal(path=path, action=action, content=body,
                               marks_ok=marks_ok, sources=sources))
    return out


def _read_note_content(project_name: str, path: str) -> str:
    """Lee el contenido actual de una nota del proyecto (best-effort)."""
    try:
        from services import doc_indexer
        return doc_indexer.read_project_doc_content(path, project_name=project_name)
    except Exception as exc:
        logger.warning("doc_documenter: no se pudo leer nota %s: %s", path, exc)
        return ""


def _sistema_readonly_block(project_name: str) -> dict:
    """Bloque read-only con el índice canónico docs/sistema/ (para linkear, NO editar)."""
    return {
        "id": "sistema-readonly",
        "kind": "canonical-index",
        "title": "docs/sistema/ (canónico — NO EDITAR, solo linkear)",
        "content": ("La documentación canónica vive en docs/sistema/. Es read-only "
                    "para el Documentador: podés linkearla con wikilinks, NUNCA "
                    "sobrescribirla ni duplicar su contenido."),
        "source": {"type": "canonical", "readonly": True},
    }


def _subgraph_block(project_name: str) -> dict:
    """Subgrafo (nodos + huérfanas) para proponer wikilinks faltantes."""
    try:
        from services import doc_graph
        g = doc_graph.build_graph(project_name=project_name)
        notes = [n["path"] for n in g.get("nodes", [])
                 if n.get("kind") == "note"
                 and str(n.get("source_id", "")).startswith("project-docs")]
        orphans = g.get("orphans", [])
        content = ("Notas del proyecto: " + ", ".join(notes[:200]) +
                   "\nHuérfanas (sin links): " + ", ".join(str(o) for o in orphans[:200]))
    except Exception as exc:
        logger.warning("doc_documenter: subgrafo no disponible: %s", exc)
        content = ""
    return {"id": "doc-subgraph", "kind": "doc-subgraph",
            "title": "Subgrafo documental", "content": content}


def _module_context_block(project_name: str, module: str) -> dict:
    """Bloque de contexto para RECONSTRUIR/COMPLETAR un módulo (árbol + símbolos)."""
    return {
        "id": f"module-{module}",
        "kind": "module-tree",
        "title": f"Módulo: {module}",
        "content": f"Documentá el módulo '{module}'. Citá archivo:línea del código real.",
        "source": {"type": "module", "module": module},
    }


def build_context_for_mode(mode: DocumenterMode, plan: DocumenterPlan,
                           project_name: str) -> list[dict]:
    """Arma los context_blocks para un modo. Siempre incluye el bloque canónico read-only."""
    blocks: list[dict] = []
    if mode == DocumenterMode.NORMALIZAR:
        for path in plan.notes_to_normalize:
            blocks.append({
                "id": f"note-{path}",
                "kind": "existing-note",
                "title": path,
                "content": _read_note_content(project_name, path),
                "source": {"type": "note", "path": path},
            })
    elif mode in (DocumenterMode.RECONSTRUIR, DocumenterMode.COMPLETAR):
        targets = plan.uncovered_modules or ["<repo>"]
        for module in targets:
            blocks.append(_module_context_block(project_name, module))
    elif mode == DocumenterMode.ENRIQUECER:
        blocks.append(_subgraph_block(project_name))
    # ACTUALIZAR (plan 114): tolerado, sin contexto especial acá.
    blocks.append(_sistema_readonly_block(project_name))
    return blocks


_CONVERSATION_ADO_ID = -7  # discriminador de identidad de tickets del Documentador


def _ensure_documenter_ticket(project_name: str) -> int:
    """Crea o reusa un ticket de conversación del Documentador para el proyecto.

    Espeja el patrón de api/devops_agent.start_conversation (ado_id discriminador +
    external_id=-ticket.id único negativo). Reusa el ticket existente si ya hay uno.
    """
    from db import session_scope
    from models import Ticket
    title = f"[Documentador] {project_name}"
    with session_scope() as session:
        existing = (session.query(Ticket)
                    .filter_by(ado_id=_CONVERSATION_ADO_ID, stacky_project_name=project_name)
                    .order_by(Ticket.id).first())
        if existing is not None:
            return existing.id
        ticket = Ticket(
            ado_id=_CONVERSATION_ADO_ID,
            project=project_name,
            stacky_project_name=project_name,
            title=title,
            work_item_type="Task",
            ado_state="Active",
        )
        session.add(ticket)
        session.flush()
        ticket.external_id = -ticket.id
        session.flush()
        return ticket.id


def _wait_and_read_output(execution_id: int, timeout_s: int = _INVOKE_TIMEOUT_S) -> str:
    """Espera a que la ejecución termine (patrón infra de ejecuciones) y lee su output.

    Poll de AgentExecution.status hasta un estado terminal o timeout. Devuelve el
    texto de salida ("" si vacío/timeout). Nunca crashea.
    """
    import time
    from db import session_scope
    from models import AgentExecution
    deadline = time.time() + max(1, timeout_s)
    terminal = {"completed", "failed", "cancelled", "error"}
    while time.time() < deadline:
        try:
            with session_scope() as s:
                ex = s.get(AgentExecution, execution_id)
                status = (ex.status if ex else "") or ""
                output = (ex.output if ex else "") or ""
            if status in terminal:
                return output
        except Exception as exc:
            logger.warning("doc_documenter: error leyendo ejecución %s: %s", execution_id, exc)
            return ""
        time.sleep(1.0)
    logger.warning("doc_documenter: timeout esperando ejecución %s", execution_id)
    return ""


def invoke_documenter(mode: DocumenterMode, context_blocks: list[dict],
                      project_name: str, runtime: str) -> list[DocProposal]:
    """Invoca al agente Documentador para un modo y devuelve las propuestas parseadas.

    Fallo/timeout → lista vacía (el run sigue con el modo siguiente).
    """
    import agent_runner
    from config import config as _config
    ticket_id = _ensure_documenter_ticket(project_name)
    # Fallback de persona built-in si el .agent.md no está (patrón plan 112 F5).
    system_override = _DEFAULT_DOCUMENTADOR_PROMPT
    try:
        execution_id = agent_runner.run_agent(
            agent_type="Documentador",
            ticket_id=ticket_id,
            context_blocks=context_blocks,
            user="documenter",
            runtime=runtime,
            vscode_agent_filename="Documentador.agent.md",
            system_prompt_override=system_override,
            project_name=project_name,
            use_few_shot=False,
            use_anti_patterns=False,
            work_item_type="Doc",
        )
    except Exception as exc:
        logger.warning("doc_documenter: run_agent falló en modo %s: %s", mode, exc)
        return []
    raw = _wait_and_read_output(execution_id)
    return parse_proposals(raw)


# ---------------------------------------------------------------------------
# F3 — Gate git: rama revertible (prepare / keep / discard). Nunca push/merge/stash.
# ---------------------------------------------------------------------------

_BRANCH_PREFIX = "stacky/doc-"


def _git(target_root: str, *args: str) -> subprocess.CompletedProcess:
    """Corre git -C target_root <args>. NUNCA incluye push/merge/stash (chequeado)."""
    forbidden = {"push", "merge", "stash"}
    if forbidden & set(args):
        raise ValueError(f"git op prohibida en doc_documenter: {args}")
    return subprocess.run(["git", "-C", target_root, *args],
                          capture_output=True, text=True)


def _is_git_repo(target_root: str) -> bool:
    r = _git(target_root, "rev-parse", "--is-inside-work-tree")
    return r.returncode == 0 and "true" in (r.stdout or "").lower()


def prepare_doc_branch(target_root: str) -> str | None:
    """Crea una rama 'stacky/doc-<UTCstamp>' en un worktree temporal aislado.

    NO toca el working tree del operador (usa `git worktree add`). Devuelve el PATH
    del worktree (donde se escribe) o None si target_root no es repo git (→ el caller
    degrada a carpeta-sombra). Nunca push/merge/stash.
    """
    if not _is_git_repo(target_root):
        return None
    _git(target_root, "worktree", "prune")  # (C5) limpia worktrees zombie
    branch = _BRANCH_PREFIX + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    tmp_worktree = tempfile.mkdtemp(prefix="stacky-doc-")
    r = _git(target_root, "worktree", "add", "-b", branch, tmp_worktree, "HEAD")
    if r.returncode != 0:
        logger.warning("doc_documenter: worktree add falló: %s", (r.stderr or "").strip())
        return None
    return tmp_worktree


def branch_of_worktree(worktree: str) -> str | None:
    """Nombre de la rama activa en un worktree (git rev-parse --abbrev-ref HEAD)."""
    r = _git(worktree, "rev-parse", "--abbrev-ref", "HEAD")
    return (r.stdout or "").strip() or None if r.returncode == 0 else None


def _worktree_for_branch(target_root: str, branch: str) -> str | None:
    r = _git(target_root, "worktree", "list", "--porcelain")
    cur: str | None = None
    for line in (r.stdout or "").splitlines():
        if line.startswith("worktree "):
            cur = line[len("worktree "):].strip()
        elif line.startswith("branch ") and line.strip().endswith("/" + branch):
            return cur
    return None


def keep_doc_branch(target_root: str, branch: str) -> None:
    """Conserva la rama para que el operador la mergee cuando quiera (NO merge, NO push).

    Solo remueve el worktree temporal; la rama queda intacta y disponible.
    """
    wt = _worktree_for_branch(target_root, branch)
    if wt:
        _git(target_root, "worktree", "remove", "--force", wt)


def discard_doc_branch(target_root: str, branch: str) -> None:
    """Borra el worktree temporal y la rama. El working tree del operador nunca se tocó."""
    wt = _worktree_for_branch(target_root, branch)
    if wt:
        _git(target_root, "worktree", "remove", "--force", wt)
    _git(target_root, "branch", "-D", branch)


# ---------------------------------------------------------------------------
# F4 — Aplicador determinista: escribe a la rama, protege lo canónico, exige marcas
# ---------------------------------------------------------------------------

import posixpath  # noqa: E402


@dataclass
class ApplyResult:
    written: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (path, reason)
    branch: str | None = None
    degraded: bool = False


def _safe_rel_path(path: str) -> str | None:
    """Normaliza a relativo POSIX seguro; None si es absoluto o escapa (anti-traversal)."""
    p = (path or "").replace("\\", "/").strip()
    if not p or p.startswith("/") or ":" in p.split("/")[0]:
        return None
    norm = posixpath.normpath(p)
    if norm.startswith("..") or norm.startswith("/") or ".." in norm.split("/"):
        return None
    return norm


def _is_canonical(norm: str) -> bool:
    """True si el path cae bajo docs/sistema/ (canónico, read-only)."""
    return norm == "docs/sistema" or "docs/sistema/" in (norm + "/")


def apply_proposals(proposals: list[DocProposal], target_root: str,
                    branch_name: str | None, *, degraded: bool = False) -> ApplyResult:
    """Valida y escribe las propuestas bajo target_root (worktree o carpeta-sombra).

    Reglas duras (rechazo = skip con razón, nunca crashea): anti-traversal,
    docs/sistema/ read-only, marcas obligatorias, tope de archivos, upsert idempotente.
    """
    from pathlib import Path as _Path
    from config import config as _config
    max_files = int(getattr(_config, "STACKY_DOCS_DOCUMENTER_MAX_FILES", 40))
    result = ApplyResult(branch=branch_name, degraded=degraded)
    root = _Path(target_root)

    for prop in proposals:
        if len(result.written) >= max_files:
            result.skipped.append((prop.path, "max_files_cap"))
            continue
        norm = _safe_rel_path(prop.path)
        if norm is None:
            result.skipped.append((prop.path, "unsafe_path"))
            continue
        if _is_canonical(norm):
            result.skipped.append((prop.path, "canonical_readonly"))
            continue
        if not prop.marks_ok:
            result.skipped.append((prop.path, "missing_confidence_marks"))
            continue
        try:
            dest = (root / norm)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(prop.content, encoding="utf-8")  # upsert: create==patch (overwrite)
            result.written.append(norm)
        except Exception as exc:
            logger.warning("doc_documenter: no se pudo escribir %s: %s", norm, exc)
            result.skipped.append((prop.path, f"write_error:{exc}"))
    return result


# ---------------------------------------------------------------------------
# F5 — Orquestador (background) + salud recomputada sobre la rama
# ---------------------------------------------------------------------------

import threading  # noqa: E402
import uuid  # noqa: E402


class DocumenterBusy(Exception):
    """Ya hay un run del Documentador en curso (lock de un solo run activo, C5)."""


_run_registry: dict[str, dict] = {}
_registry_lock = threading.Lock()


def _resolve_target_paths(project_name: str) -> tuple[str | None, str | None, str | None]:
    """(target_root, docs_root, workspace_root) del proyecto activo, vía doc_indexer."""
    from services import doc_indexer
    info = doc_indexer.list_doc_sources(project_name)
    workspace_root = info.get("workspace_root")
    docs_root = None
    for s in info.get("sources", []) or []:
        if str(s.get("id", "")).startswith("project-docs") and s.get("absolute_path"):
            docs_root = s["absolute_path"]
            break
    target_root = workspace_root or docs_root
    return target_root, docs_root, workspace_root


def _health_for_root(docs_root: str | None, workspace_root: str | None = None) -> dict:
    """(C4) Recalcula doc_health sobre una carpeta de docs arbitraria, sin cache.

    Enumera *.md bajo docs_root, arma nodos/aristas con los parsers PUROS del 109
    y llama classify_doc_health. Nunca lanza."""
    from services import doc_graph
    try:
        if not docs_root:
            return {"status": "SIN_DOCS", "reasons": [], "frontmatter_ratio": 0.0,
                    "wikilink_edges": 0, "uncovered_modules": []}
        root = Path(docs_root)
        if not root.is_dir():
            return {"status": "SIN_DOCS", "reasons": [], "frontmatter_ratio": 0.0,
                    "wikilink_edges": 0, "uncovered_modules": []}
        nodes: list[dict] = []
        edges: list[dict] = []
        for md in sorted(root.rglob("*.md")):
            rel = str(md.relative_to(root)).replace("\\", "/")
            try:
                content = md.read_text(encoding="utf-8-sig", errors="ignore")
            except OSError:
                content = ""
            node_id = f"note:project-docs:local:{rel}"
            nodes.append({
                "id": node_id, "kind": "note", "path": rel,
                "source_id": "project-docs:local",
                "has_frontmatter": bool(content) and content.lstrip().startswith("---"),
            })
            for _ in doc_graph.parse_markdown_links(content):
                edges.append({"source": node_id, "target": "note:x", "kind": "md"})
            for _ in doc_graph.parse_wikilinks(content):
                edges.append({"source": node_id, "target": "note:x", "kind": "wikilink"})
            for ref in doc_graph.parse_code_refs(content):
                edges.append({"source": node_id, "target": f"code:{ref}", "kind": "code_ref"})
        return doc_graph.classify_doc_health(nodes, edges, workspace_root)
    except Exception as exc:
        logger.warning("doc_documenter: _health_for_root fallo: %s", exc)
        return {"status": "SANA", "reasons": [], "frontmatter_ratio": 0.0,
                "wikilink_edges": 0, "uncovered_modules": []}


def _new_run_record(project_name: str, runtime: str) -> dict:
    return {"state": "running", "project": project_name, "runtime": runtime,
            "current_mode": None, "written": [], "skipped": [],
            "health_before": None, "health_after": None, "branch": None,
            "degraded": False, "diff_stat": "", "target_root": None,
            "worktree": None, "error": None, "reason": ""}


def start_documenter_run(project_name: str, runtime: str) -> str:
    """Lanza el pipeline en background. DocumenterBusy si ya hay uno activo (C5)."""
    with _registry_lock:
        if any(r.get("state") == "running" for r in _run_registry.values()):
            raise DocumenterBusy()
        run_id = uuid.uuid4().hex[:12]
        _run_registry[run_id] = _new_run_record(project_name, runtime)
    t = threading.Thread(target=_run_documenter_thread,
                         args=(run_id, project_name, runtime), daemon=True)
    t.start()
    return run_id


def _update_run(run_id: str, **fields) -> None:
    with _registry_lock:
        rec = _run_registry.get(run_id)
        if rec is not None:
            rec.update(fields)


def get_run(run_id: str) -> dict | None:
    with _registry_lock:
        rec = _run_registry.get(run_id)
        return dict(rec) if rec is not None else None


def _run_documenter_thread(run_id: str, project_name: str, runtime: str) -> None:
    try:
        run_documenter(project_name, runtime, run_id=run_id)
    except Exception as exc:  # noqa: BLE001 - nunca deja el run colgado
        logger.error("doc_documenter: run %s fallo: %s", run_id, exc, exc_info=True)
        _update_run(run_id, state="failed", error=str(exc))


def run_documenter(project_name: str, runtime: str, *, run_id: str | None = None) -> dict:
    """Ejecuta el pipeline completo (sincrono). Devuelve el report dict."""
    plan = plan_documenter_run(project_name)
    target_root, docs_root, workspace_root = _resolve_target_paths(project_name)
    if run_id:
        _update_run(run_id, target_root=target_root, reason=plan.reason)

    health_before = _health_for_root(docs_root, workspace_root)
    worktree = prepare_doc_branch(target_root) if target_root else None
    degraded = worktree is None
    if worktree:
        write_root = worktree
        branch = branch_of_worktree(worktree)
    else:
        base = target_root or docs_root or "."
        write_root = str(Path(base) / ".stacky-docs-proposed")
        Path(write_root).mkdir(parents=True, exist_ok=True)
        branch = None
    if run_id:
        _update_run(run_id, branch=branch, degraded=degraded, worktree=worktree)

    all_props: list[DocProposal] = []
    for mode in plan.modes:
        if run_id:
            _update_run(run_id, current_mode=str(mode.value))
        ctx = build_context_for_mode(mode, plan, project_name)
        props = invoke_documenter(mode, ctx, project_name, runtime)
        all_props += props

    result = apply_proposals(all_props, write_root, branch, degraded=degraded)

    diff_stat = ""
    if worktree and not degraded:
        try:
            _git(worktree, "add", "-A")
            diff_stat = (_git(worktree, "diff", "--stat", "--cached", "HEAD").stdout or "")
            _git(worktree, "commit", "-m", f"docs: Documentador ({run_id or 'run'})")
        except Exception as exc:
            logger.warning("doc_documenter: no se pudo commitear la rama doc: %s", exc)

    after_docs = worktree if worktree else write_root
    if worktree and docs_root and target_root:
        try:
            rel = Path(docs_root).relative_to(Path(target_root))
            after_docs = str(Path(worktree) / rel)
        except Exception:
            after_docs = worktree
    health_after = _health_for_root(after_docs, workspace_root)

    report = {
        "state": "completed",
        "reason": plan.reason,
        "modes": [str(m.value) for m in plan.modes],
        "written": result.written,
        "skipped": result.skipped,
        "health_before": health_before,
        "health_after": health_after,
        "branch": branch,
        "degraded": degraded,
        "diff_stat": diff_stat,
        "target_root": target_root,
        "worktree": worktree,
    }
    if run_id:
        _update_run(run_id, **report)
    return report
