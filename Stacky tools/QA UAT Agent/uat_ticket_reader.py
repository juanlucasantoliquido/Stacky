"""
uat_ticket_reader.py — Reads an ADO ticket and returns a normalized JSON for the UAT pipeline.

SPEC: SPEC/uat_ticket_reader.md
CLI:
    python uat_ticket_reader.py --ticket 70 [--cache] [--ado-path <path>] [--verbose]

Output: JSON to stdout following uat_ticket.schema.json
Errors: {"ok": false, "error": "<code>", "message": "..."} with exit code 1
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.ticket_reader")

# ── Constants ─────────────────────────────────────────────────────────────────

_TOOL_VERSION = "1.0.0"


def _resolve_sibling_tool(tool_dir_name: str, entrypoint: str) -> Path:
    """Locate a sibling tool by walking up to the `Stacky tools` container.

    See qa_uat_pipeline._resolve_sibling_tool for full rationale.
    """
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        if ancestor.name == "Stacky tools":
            return ancestor / tool_dir_name / entrypoint
    return Path(__file__).resolve().parent.parent / tool_dir_name / entrypoint


_DEFAULT_ADO_PATH = _resolve_sibling_tool("ADO Manager", "ado.py")

# Keywords to classify comment roles (fallback regex)
_ROLE_KEYWORDS: dict[str, list[str]] = {
    "analisis_tecnico": [
        "análisis técnico", "analisis tecnico", "technical analysis",
        "análisis técnico:", "analisis tecnico:", "## análisis técnico",
        "## analisis tecnico", "plan de pruebas", "plan de prueba",
        "TU-0", "P01", "P02", "P03",
    ],
    "analisis_funcional": [
        "análisis funcional", "analisis funcional", "functional analysis",
        "## análisis funcional", "## analisis funcional",
    ],
    "implementacion": [
        "implementación", "implementacion", "implementation",
        "## implementación", "## implementacion", "cambios realizados",
        "archivos modificados",
    ],
    "qa": [
        "qa", "quality assurance", "prueba", "testing",
        "evidencia", "resultado de qa", "resultado qa",
    ],
}

# Regex to extract P01..P0N items from plan de pruebas section
_PLAN_ITEM_RE = re.compile(
    r'\*?\*?(?:P|Caso\s+)(\d{2,3})[:.)][ \t]*([^\n]+(?:\n(?![ \t]*\*?\*?(?:P|Caso\s+)\d{2,3}[:.)]).*)*)',
    re.MULTILINE,
)
_DATOS_RE = re.compile(r'[Dd]atos?[:\s]+([^\n]+)')
_ESPERADO_RE = re.compile(r'[Ee]sperado?[:\s]+([^\n]+)')

# Detect precondition types
_RIDIOMA_RE = re.compile(r'INSERT\s+INTO\s+RIDIOMA', re.IGNORECASE)
_WEB_CONFIG_RE = re.compile(r'Web\.config|webconfig|appSettings', re.IGNORECASE)
_SQL_SCRIPT_RE = re.compile(r'\.sql\b|exec\s+\w+|EXEC\s+', re.IGNORECASE)
_BUILD_DEPLOY_RE = re.compile(r'compilar|compilación|build|deploy|desplegar', re.IGNORECASE)

# Max text to send to LLM for comment classification
_LLM_MAX_CHARS = 2000


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = _parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, stream=sys.stderr,
                            format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, stream=sys.stderr)

    result = run(
        ticket_id=args.ticket,
        use_cache=args.cache,
        ado_path=Path(args.ado_path) if args.ado_path else None,
        verbose=args.verbose,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("ok") else 1)


def run(
    ticket_id: int,
    use_cache: bool = False,
    ado_path: Optional[Path] = None,
    verbose: bool = False,
) -> dict:
    """Core logic — callable from tests without subprocess."""
    started = time.time()
    ado_path = ado_path or _DEFAULT_ADO_PATH

    # Validate ticket id
    if not isinstance(ticket_id, int) or ticket_id < 1:
        return _err("invalid_id", f"ticket_id must be a positive integer, got: {ticket_id!r}")

    evidence_dir = Path(__file__).resolve().parent / "evidence" / str(ticket_id)
    evidence_dir.mkdir(parents=True, exist_ok=True)
    cache_file = evidence_dir / "ticket.json"

    # --cache: return existing file if present
    if use_cache and cache_file.is_file():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            logger.debug("cache hit for ticket %d", ticket_id)
            return cached
        except Exception as exc:
            logger.warning("cache file corrupt, re-reading ADO: %s", exc)

    # Call ADO Manager: get + comments
    ticket_data = _ado_get(ado_path, ticket_id)
    if not ticket_data.get("ok"):
        return _err("ado_error", ticket_data.get("message", str(ticket_data)))

    wi = (ticket_data.get("work_item") or ticket_data.get("item")
          or ticket_data.get("result") or {})
    if not wi:
        # ticket_data might be the work item directly
        if ticket_data.get("id"):
            wi = ticket_data
        else:
            return _err("ticket_not_found", f"ADO returned no work item for ticket {ticket_id}")

    comments_data = _ado_comments(ado_path, ticket_id)
    if not comments_data.get("ok"):
        return _err("ado_error", comments_data.get("message", str(comments_data)))

    raw_comments = (comments_data.get("comments")
                    or comments_data.get("result")
                    or [])

    # Classify comments
    classified = _classify_comments(raw_comments, verbose=verbose)

    # Find analisis_tecnico
    tecnico_comment = next(
        (c for c in classified if c["role"] == "analisis_tecnico"), None
    )
    if tecnico_comment is None:
        return _err("missing_technical_analysis",
                    "No comment classified as analisis_tecnico found in ticket")

    analisis_text = _html_to_text(tecnico_comment["text_md"])

    # Extract plan de pruebas
    plan_pruebas = _extract_plan_pruebas(analisis_text)
    if not plan_pruebas:
        return _err("no_test_plan_in_ticket",
                    "Could not extract P01..P0N items from analisis_tecnico comment")

    # Extract notas_qa
    notas_qa = _extract_notas_qa(classified)

    # Extract adjuntos
    adjuntos = _extract_adjuntos(wi)

    # Detect preconditions
    full_text = analisis_text + "\n".join(notas_qa)
    precondiciones = _detect_preconditions(full_text)

    result: dict = {
        "ok": True,
        "ticket": {
            "id": int(wi.get("id") or ticket_id),
            "title": str(wi.get("title") or wi.get("fields", {}).get("System.Title", "")),
            "state": str(wi.get("state") or wi.get("fields", {}).get("System.State", "")),
            "type": str(wi.get("type") or wi.get("fields", {}).get("System.WorkItemType", "Task")),
            "url": str(wi.get("url") or wi.get("_links", {}).get("html", {}).get("href", "")),
        },
        "description_md": str(wi.get("description") or wi.get("fields", {}).get("System.Description", "")),
        "comments": classified,
        "analisis_tecnico": analisis_text,
        "plan_pruebas": plan_pruebas,
        "notas_qa": notas_qa,
        "adjuntos": adjuntos,
        "precondiciones_detected": precondiciones,
        "meta": {
            "tool": "uat_ticket_reader",
            "version": _TOOL_VERSION,
            "duration_ms": int((time.time() - started) * 1000),
        },
    }

    # Persist to evidence/<ticket>/ticket.json
    try:
        cache_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not persist ticket.json: %s", exc)

    return result


# ── ADO Manager wrappers ───────────────────────────────────────────────────────

def _ado_run(ado_path: Path, args: list) -> dict:
    """Invoke ado.py via subprocess and return parsed JSON output."""
    import os
    cmd = [sys.executable, str(ado_path)] + args
    logger.debug("ado cmd: %s", " ".join(cmd))
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30, check=False, env=env
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "ADO Manager timed out"}
    except FileNotFoundError:
        return {"ok": False, "message": f"ado.py not found at {ado_path}"}

    if proc.returncode not in (0, 1):
        return {"ok": False, "message": f"ado.py exited {proc.returncode}: {proc.stderr[:300]}"}

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"ok": False, "message": f"ado.py output not JSON: {exc} — {proc.stdout[:200]}"}


def _ado_get(ado_path: Path, ticket_id: int) -> dict:
    return _ado_run(ado_path, ["get", str(ticket_id)])


def _ado_comments(ado_path: Path, ticket_id: int) -> dict:
    return _ado_run(ado_path, ["comments", str(ticket_id)])


# ── Comment classification ─────────────────────────────────────────────────────

def _classify_comments(raw_comments: list, verbose: bool = False) -> list:
    """Classify each comment as one of the role enum values."""
    classified = []
    for i, c in enumerate(raw_comments):
        if not isinstance(c, dict):
            continue
        text = str(c.get("text") or c.get("content") or c.get("text_md") or "")
        role = _classify_role(text, verbose=verbose)
        classified.append({
            "id": int(c.get("id") or i + 1),
            "author": str(c.get("author") or c.get("createdBy", {}).get("displayName", "")),
            "date": str(c.get("date") or c.get("createdDate") or ""),
            "text_md": text,
            "role": role,
        })
    return classified


def _classify_role(text: str, verbose: bool = False) -> str:
    """Classify a comment text into one of the role enum values."""
    lower = text.lower()

    # Deterministic regex fallback — check keyword presence
    for role, keywords in _ROLE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in lower:
                logger.debug("classified as %s via regex keyword %r", role, kw)
                return role

    # Try LLM classification
    try:
        from llm_client import call_llm, LLMError
        snippet = text[:_LLM_MAX_CHARS]
        system_prompt = (
            "You are a comment classifier for Azure DevOps work items. "
            "Classify the following comment into exactly one of these roles: "
            "analisis_funcional, analisis_tecnico, implementacion, qa, otros. "
            "Respond with ONLY a JSON object: {\"role\": \"<role>\"}. No explanations."
        )
        result = call_llm(
            model="gpt-4.1-mini",
            system=system_prompt,
            user=f"Comment text:\n{snippet}",
            max_tokens=64,
        )
        parsed = json.loads(result["text"])
        role = parsed.get("role", "otros")
        valid_roles = {"analisis_funcional", "analisis_tecnico", "implementacion", "qa", "otros"}
        if role in valid_roles:
            logger.debug("LLM classified comment as %r", role)
            return role
    except Exception as exc:
        logger.debug("LLM classification failed, defaulting to 'otros': %s", exc)

    return "otros"


# ── Plan de pruebas extraction ────────────────────────────────────────────────

def _extract_plan_pruebas(text: str) -> list:
    """Extract P01..P0N items from analisis_tecnico text."""
    items = []
    seen_ids: set = set()

    for m in _PLAN_ITEM_RE.finditer(text):
        pid = f"P{m.group(1).zfill(2)}"
        if pid in seen_ids:
            continue
        seen_ids.add(pid)
        full_block = m.group(0)
        # First line is the title/description
        lines = full_block.strip().split("\n")
        desc = re.sub(r'^\*?\*?(?:P|Caso\s+)\d{2,3}[:\.\)]\*?\*?\s*', '', lines[0]).strip()

        datos_m = _DATOS_RE.search(full_block)
        esperado_m = _ESPERADO_RE.search(full_block)

        item = {
            "id": pid,
            "descripcion": desc or full_block[:120],
        }
        if datos_m:
            item["datos"] = datos_m.group(1).strip()
        if esperado_m:
            item["esperado"] = esperado_m.group(1).strip()
        items.append(item)

    return items


def _extract_notas_qa(classified: list) -> list:
    """Extract QA notes from comments classified as 'qa'."""
    notas = []
    for c in classified:
        if c["role"] in ("qa", "analisis_tecnico"):
            text = _html_to_text(c["text_md"])
            # Look for notes sections
            for line in text.split("\n"):
                line = line.strip()
                if line and any(
                    kw in line.lower()
                    for kw in ("nota para qa", "nota qa", "aplicar", "insert", "ridioma")
                ):
                    notas.append(line)
    return notas


def _extract_adjuntos(wi: dict) -> list:
    """Extract attachments from work item."""
    adjuntos = []
    # ADO Manager may return attachments in different structures
    relations = wi.get("relations") or []
    for rel in relations:
        if "AttachedFile" in str(rel.get("rel", "")):
            attrs = rel.get("attributes") or {}
            adjuntos.append({
                "name": attrs.get("name", "attachment"),
                "url": rel.get("url", ""),
            })
    return adjuntos


# ── Precondition detection ────────────────────────────────────────────────────

def _detect_preconditions(text: str) -> list:
    """Detect preconditions mentioned in the ticket analysis text."""
    preconditions = []

    # RIDIOMA INSERTs
    for m in re.finditer(r'(INSERT\s+INTO\s+RIDIOMA[^;\n]*(?:;|$))', text, re.IGNORECASE | re.MULTILINE):
        preconditions.append({
            "tipo": "RIDIOMA_INSERT",
            "recurso": _extract_ridioma_id(m.group(1)),
            "evidencia": m.group(1).strip()[:200],
        })

    # Web.config flags
    for m in re.finditer(r'(Web\.config\s*[:\-]?\s*[^,\n]+)', text, re.IGNORECASE):
        preconditions.append({
            "tipo": "WEB_CONFIG_FLAG",
            "recurso": m.group(1).strip()[:100],
        })

    # BUILD_DEPLOY
    if _BUILD_DEPLOY_RE.search(text):
        preconditions.append({
            "tipo": "BUILD_DEPLOY",
            "recurso": "AgendaWeb.sln",
        })

    return preconditions


def _extract_ridioma_id(insert_stmt: str) -> str:
    """Try to extract IDTEXTO or key from INSERT statement."""
    m = re.search(r'IDTEXTO\s*=\s*(\d+)', insert_stmt, re.IGNORECASE)
    if m:
        return f"IDTEXTO={m.group(1)}"
    return insert_stmt[:60]


# ── Utilities ─────────────────────────────────────────────────────────────────

def _html_to_text(html: str) -> str:
    """Strip HTML tags for text processing, preserving line breaks."""
    text = html or ''
    # Convert block-level tags to newlines first
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</p\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</h[1-6]\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</li\s*>', '\n', text, flags=re.IGNORECASE)
    text = re.sub(r'</tr\s*>', '\n', text, flags=re.IGNORECASE)
    # Strip remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    text = re.sub(r'&amp;', '&', text)
    # Collapse multiple spaces on same line but keep newlines
    lines = text.split('\n')
    lines = [re.sub(r' {2,}', ' ', line).strip() for line in lines]
    return '\n'.join(lines).strip()


def _err(code: str, message: str) -> dict:
    return {"ok": False, "error": code, "message": message}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="uat_ticket_reader — Read ADO ticket for UAT pipeline"
    )
    parser.add_argument("--ticket", type=int, required=True, help="ADO work item ID")
    parser.add_argument("--cache", action="store_true",
                        help="Return cached evidence/<id>/ticket.json if present")
    parser.add_argument("--ado-path", type=str, default=None,
                        help=f"Path to ado.py (default: {_DEFAULT_ADO_PATH})")
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    main()
