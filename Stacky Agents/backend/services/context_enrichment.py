"""Pipeline de enriquecimiento de contexto reutilizable.

Extrae la lógica que vivía inline en `agent_runner._run_in_background` para que
TODOS los runtimes (github_copilot, codex_cli, claude_code_cli) inyecten el mismo
contexto: estructura de épica, artifacts en disco, tickets similares y comentarios
/adjuntos de ADO.

Contrato: `enrich_blocks(...)` es una función pura respecto a los `raw_blocks`
(no muta la lista de entrada; devuelve una nueva) y nunca lanza: cada paso de
enriquecimiento es best-effort y se degrada con un warning en el `log`. Devuelve
`(enriched_blocks, ado_enrich_stats)` donde `ado_enrich_stats` es el dict de
contadores de ADO (o None si el ticket no tiene `ado_id`).

El comportamiento es idéntico al que tenía github_copilot inline: los mismos
gates por `agent_type`, las mismas env vars y el mismo orden de inyección. El
PII masking NO se hace acá (lo aplica cada runner sobre el resultado, porque
github_copilot necesita el `mask_map` para re-hidratar el output).
"""
from __future__ import annotations

import os
from typing import Any, Callable

from db import session_scope
from models import AgentExecution, Ticket

# Plan 67 — disciplina de procesos
from services import process_discipline

LogFn = Callable[..., None]


def _noop_log(*_args: Any, **_kwargs: Any) -> None:  # pragma: no cover - trivial
    pass


# Plan 64 F2 — Cache en-memoria: content_hash -> RagIndex. Se invalida automáticamente cuando
# el catálogo cambia (hash distinto). Usa un único slot (clear en cada cambio).
# Thread-safety: no es safe para gunicorn multi-worker (cada worker tiene su propia
# copia del proceso; para Stacky single-worker es OK).
_RAG_INDEX_CACHE: dict = {}


def _get_rag_index(catalog: list[dict]):  # type: ignore[return]
    """Devuelve el índice TF-IDF del catálogo; lo construye si el hash cambió."""
    import hashlib
    import json
    from services.rag_retriever import build_index, chunks_from_process_catalog

    content_hash = hashlib.md5(
        json.dumps(catalog, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    if content_hash not in _RAG_INDEX_CACHE:
        chunks = chunks_from_process_catalog(catalog)
        _RAG_INDEX_CACHE.clear()  # máximo 1 entrada; libera si cambió el catálogo
        _RAG_INDEX_CACHE[content_hash] = build_index(chunks, content_hash=content_hash)
    return _RAG_INDEX_CACHE[content_hash]


def enrich_blocks(
    *,
    ticket_id: int | None,
    agent_type: str,
    raw_blocks: list[dict] | None,
    project_ctx: Any = None,
    log: LogFn | None = None,
) -> tuple[list[dict], dict | None]:
    """Aplica el pipeline de enriquecimiento y devuelve (blocks, ado_stats).

    Orden (idéntico al flujo histórico de github_copilot):
      1. ado-epic-structured   (solo functional + ticket Epic)
      2. filesystem-artifacts  (artifact_context)
      3. ado-similar-tickets   (functional/technical, requiere ado_id)
      4. ado-comments/adjuntos (ado_context.enrich, requiere ado_id)
    """
    log = log or _noop_log
    blocks: list[dict] = list(raw_blocks or [])

    # Capturar escalares del ticket en una sesión propia (evita DetachedInstanceError).
    ticket_ado_id: int | None = None
    ticket_project: str | None = None
    ticket_title: str | None = None
    ticket_description: str | None = None
    ticket_obj = None
    with session_scope() as _sess:
        ticket_obj = _sess.get(Ticket, ticket_id) if ticket_id else None
        if ticket_obj is not None:
            ticket_ado_id = ticket_obj.ado_id
            ticket_project = ticket_obj.project
            ticket_title = ticket_obj.title
            ticket_description = ticket_obj.description

    project_name = (project_ctx.stacky_project_name if project_ctx else None) or ticket_project

    # Plan 64 F2 — query para RAG (disponible desde el inicio del pipeline)
    _rag_query = " ".join(p for p in [ticket_title, ticket_description] if p) or None

    # Memoria Stacky: PREPEND explícito para que sea el primer bloque de
    # contexto. Flag OFF por default; best-effort para no alterar runs existentes.
    blocks = _inject_stacky_memory_block(
        blocks=blocks,
        project_name=project_name,
        ticket_id=ticket_id,
        agent_type=agent_type,
        log=log,
    )
    # Plan 16: inyectar primero el client-profile (si está disponible y el
    # feature flag lo permite) para que todos los pasos siguientes puedan
    # leerlo si lo necesitan.
    blocks = _inject_client_profile_block(blocks, project_name, log)
    # Plan 42 F0 + Plan 64 F2 — diccionario de procesos (RAG si habilitado).
    blocks = _inject_process_catalog_block(blocks, project_name, log, query=_rag_query)
    # Plan 67 | 2026-06-23 | Disciplina de procesos: decidir REUSE vs CREATE
    blocks = _inject_process_discipline_block(
        blocks=blocks,
        project_name=project_name,
        title=ticket_title,
        description=ticket_description,
        log=log,
    )
    blocks = _inject_epic_structured(ticket_id, agent_type, blocks, log)
    blocks = _inject_artifact_context(ticket_id, blocks, log)

    # I3.1 — Paralelización de injectors I/O-bound independientes.
    ado_stats: dict | None = None
    from config import config as _cfg
    if getattr(_cfg, "STACKY_PARALLEL_INJECTORS_ENABLED", False):
        from concurrent.futures import ThreadPoolExecutor

        def _run_sim() -> list[dict]:
            return _inject_similar_tickets(
                ticket_id, agent_type, ticket_ado_id, [], project_name, log
            )

        def _run_ado() -> tuple[list[dict], dict | None]:
            return _inject_ado_context(
                ticket_id=ticket_id,
                agent_type=agent_type,
                ticket_ado_id=ticket_ado_id,
                blocks=[],
                project=ticket_project,
                project_ctx=project_ctx,
                project_name=project_name,
                ticket_obj=ticket_obj,
                log=log,
            )

        _sim_blocks: list[dict] = []
        _ado_blocks: list[dict] = []
        with ThreadPoolExecutor(max_workers=2) as _pool:
            _fut_sim = _pool.submit(_run_sim)
            _fut_ado = _pool.submit(_run_ado)
            try:
                _sim_result = _fut_sim.result()
                _sim_blocks = _sim_result if isinstance(_sim_result, list) else []
            except Exception as _e_sim:  # noqa: BLE001
                log("warn", f"parallel _inject_similar_tickets falló: {_e_sim}")
            try:
                _ado_result = _fut_ado.result()
                if isinstance(_ado_result, tuple) and len(_ado_result) == 2:
                    _ado_blocks, ado_stats = _ado_result
                    if not isinstance(_ado_blocks, list):
                        _ado_blocks = []
            except Exception as _e_ado:  # noqa: BLE001
                log("warn", f"parallel _inject_ado_context falló: {_e_ado}")

        # Merge en orden canónico: base + similar + ado, dedup por ID
        blocks = list(blocks)
        _seen_ids = {b.get("id") for b in blocks if isinstance(b, dict) and b.get("id")}
        for _b in _sim_blocks:
            if isinstance(_b, dict):
                _bid = _b.get("id")
                if not _bid or _bid not in _seen_ids:
                    blocks.append(_b)
                    if _bid:
                        _seen_ids.add(_bid)
        for _b in _ado_blocks:
            if isinstance(_b, dict):
                _bid = _b.get("id")
                if not _bid or _bid not in _seen_ids:
                    blocks.append(_b)
                    if _bid:
                        _seen_ids.add(_bid)
    else:
        # Camino serial original (byte-idéntico con flag OFF)
        blocks = _inject_similar_tickets(
            ticket_id, agent_type, ticket_ado_id, blocks, project_name, log
        )
        blocks, ado_stats = _inject_ado_context(
            ticket_id=ticket_id,
            agent_type=agent_type,
            ticket_ado_id=ticket_ado_id,
            blocks=blocks,
            project=ticket_project,
            project_ctx=project_ctx,
            project_name=project_name,
            ticket_obj=ticket_obj,
            log=log,
        )

    # Q0.1 — Inyección de criterios de aceptación como checklist (OFF default).
    blocks = _inject_acceptance_criteria(
        ticket_id=ticket_id,
        project_name=project_name,
        blocks=blocks,
        log=log,
    )
    # A1.1 — Blanco del contrato de aceptación ejecutable (OFF default).
    # Alta prioridad, nunca se poda. Solo cuando mode=gate y el contrato no es n/a.
    blocks = _inject_acceptance_contract_block(
        ticket_id=ticket_id,
        project_name=project_name,
        blocks=blocks,
        log=log,
    )
    # Q1.2 — Few-shot de outputs aprobados para runtimes CLI (OFF default).
    blocks = _inject_cli_fewshot(
        ticket_id=ticket_id,
        agent_type=agent_type,
        project_name=project_name,
        blocks=blocks,
        log=log,
    )
    # Plan 48 — lecciones de rechazo del operador como anti-patrón imperativo (CLI).
    blocks = _inject_rejection_lessons(
        blocks=blocks, project_name=project_name, agent_type=agent_type, log=log
    )
    # I0.1 — dedup léxico entre bloques (antes del budget, OFF default).
    blocks = _dedup_blocks(blocks, project_name=project_name, log=log)
    # F2.4 + I2.1 — presupuesto de contexto con ranking y rerank (OFF default).
    _context_text = " ".join(p for p in [ticket_title, ticket_description] if p)
    blocks = _apply_context_budget(
        blocks, project_name=project_name, log=log, context_text=_context_text or None
    )
    return blocks, ado_stats


# ---------------------------------------------------------------------------
# I0.1 — Dedup léxico de hechos repetidos entre bloques de contexto
# ---------------------------------------------------------------------------

# Prioridad >= este umbral: la fuente de verdad. Nunca se poda.
_HIGH_PRIORITY_THRESHOLD = 75  # cubre: ado-epic-structured(100), client-profile(95),
                                # stacky-memory(80), modal_user_input(78), operator_note(76)


def _normalize_line(line: str) -> str:
    """Normaliza una línea para comparación: lowercase + colapso de espacios."""
    return " ".join(line.lower().split())


def _dedup_blocks(
    blocks: list[dict], *, project_name: str | None, log: LogFn
) -> list[dict]:
    """Elimina líneas repetidas de bloques de menor prioridad.

    Algoritmo (conservador y barato — I0.1):
      1. Si el flag está OFF → devuelve la misma lista sin tocar (byte-idéntico).
      2. Recorre los bloques de MAYOR a MENOR prioridad acumulando hashes de
         líneas normalizadas (set de seen).
      3. Para cada bloque de prioridad < _HIGH_PRIORITY_THRESHOLD, filtra las
         líneas cuyo hash normalizado ya está en seen; las demás se conservan.
      4. Los bloques de alta prioridad se acumulan en seen pero NUNCA se podan.
      5. Best-effort: cualquier excepción → bloques sin tocar, mismo contrato
         que _apply_context_budget.

    Retorna una nueva lista (no muta la entrada) si hubo cambios; la misma lista
    si no hubo cambios (flag OFF, o ninguna línea podada).
    """
    from config import config
    from services import cli_feature_flags

    # Flag global OFF → identidad estricta.
    if not getattr(config, "STACKY_CONTEXT_DEDUP_ENABLED", False):
        return blocks

    # Allowlist de proyectos (mismo patrón que context_budget_enabled).
    projects_csv: str = getattr(config, "STACKY_CONTEXT_DEDUP_PROJECTS", "") or ""
    if projects_csv.strip():
        allowed = {p.strip().lower() for p in projects_csv.split(",") if p.strip()}
        if project_name and project_name.lower() not in allowed:
            return blocks

    if not blocks:
        return blocks

    try:
        # Ordenar por prioridad DESC para acumular seen desde los más importantes.
        indexed = sorted(
            enumerate(blocks), key=lambda iv: (-_block_priority(iv[1]), iv[0])
        )

        seen_hashes: set[str] = set()
        # Índices cuyo contenido fue podado → {orig_idx: nuevo_content}
        replacements: dict[int, str] = {}

        for orig_idx, block in indexed:
            if not isinstance(block, dict):
                continue
            content = block.get("content")
            if not isinstance(content, str):
                continue

            is_high_priority = _block_priority(block) >= _HIGH_PRIORITY_THRESHOLD
            lines = content.splitlines()

            if is_high_priority:
                # Solo acumular en seen; nunca podar.
                for line in lines:
                    norm = _normalize_line(line)
                    if norm:
                        seen_hashes.add(norm)
            else:
                # Podar las líneas cuyo hash ya está en seen.
                kept_lines = []
                for line in lines:
                    norm = _normalize_line(line)
                    if norm in seen_hashes:
                        continue  # duplicado → eliminar
                    kept_lines.append(line)
                    if norm:
                        seen_hashes.add(norm)
                new_content = "\n".join(kept_lines)
                if new_content != content:
                    replacements[orig_idx] = new_content

        if not replacements:
            return blocks  # nada que cambiar → identidad

        # Construir nueva lista preservando el orden original.
        result = []
        for i, block in enumerate(blocks):
            if i in replacements:
                new_block = dict(block)
                new_block["content"] = replacements[i]
                result.append(new_block)
            else:
                result.append(block)

        removed = sum(
            len(blocks[i].get("content", "").splitlines())
            - len(replacements[i].splitlines())
            for i in replacements
        )
        log("info", f"dedup de contexto (I0.1): {removed} líneas duplicadas eliminadas "
            f"de {len(replacements)} bloque(s)")
        return result

    except Exception:  # noqa: BLE001 — best-effort, mismo contrato que budget
        return blocks


# ---------------------------------------------------------------------------
# F2.4 — Presupuesto de contexto con ranking
# ---------------------------------------------------------------------------

# Valor relativo por id de bloque (mayor = más importante, se conserva primero).
# El ticket/épica y las restricciones del cliente nunca se recortan; lo barato
# de recortar (comentarios viejos, similares) queda accesible vía MCP (F2.1).
_BLOCK_PRIORITY: dict[str, int] = {
    "operator-corrections": 110,  # Plan 41 — correcciones del operador mandan sobre todo
    "ado-epic-structured": 100,
    "client-profile": 95,
    "rejection-lessons": 82,  # Plan 48 — restricción dura (rechazos previos del operador)
    "stacky-memory": 80,
    "modal_user_input": 78,
    "operator_note": 76,
    "acceptance-criteria": 74,   # Q0.1 — alta prioridad, nunca se poda
    "filesystem-artifacts-status": 70,
    "glossary-auto": 60,
    "few-shot-approved": 55,     # Q1.2 — media-alta, podable bajo presión
    "ado-similar-tickets": 40,
    "ado-comments": 30,
    "ado-attachments": 25,
}
_DEFAULT_PRIORITY = 50
_TRUNCATION_MARKER = (
    "\n\n[recortado por presupuesto de contexto — pedí el detalle completo "
    "vía las tools MCP de Stacky si lo necesitás]"
)


def _block_priority(block: dict) -> int:
    return _BLOCK_PRIORITY.get(block.get("id") or "", _DEFAULT_PRIORITY)


def _block_token_estimate(block: dict) -> int:
    from prompt_builder import estimate_tokens

    content = block.get("content")
    text = content if isinstance(content, str) else ""
    for it in block.get("items") or []:
        if isinstance(it, dict) and it.get("selected"):
            text += "\n" + (it.get("label") or "")
    return estimate_tokens(text or "")


def _apply_context_budget(
    blocks: list[dict],
    *,
    project_name: str | None,
    log: LogFn,
    context_text: str | None = None,
) -> list[dict]:
    """Recorta bloques de menor valor para respetar un presupuesto de tokens.

    Ordena por prioridad (desc), va sumando estimaciones y, cuando se pasa del
    budget, trunca el contenido del bloque que excede (dejando un marcador) y
    descarta el resto de los bloques de menor prioridad. Preserva el orden
    original de la lista para no alterar la narrativa del prompt; solo cambia
    el contenido de los bloques recortados.

    I2.1 — Con `STACKY_CONTEXT_RERANK_ENABLED=true` y `context_text` no vacío,
    el orden de conservación mezcla prioridad fija + w * relevancia_al_ticket
    (w=0.3). Solo afecta bloques de menor prioridad (< _HIGH_PRIORITY_THRESHOLD).
    El orden de PRESENTACIÓN no cambia (la lista resultado sigue el orden original).

    Pura sobre `blocks` (no muta la entrada). Best-effort: cualquier fallo
    devuelve los bloques sin tocar.
    """
    from config import config
    from services import cli_feature_flags

    if not cli_feature_flags.context_budget_enabled(project_name):
        return blocks
    try:
        budget = int(config.STACKY_CONTEXT_BUDGET_TOKENS)
    except (TypeError, ValueError):
        return blocks
    if budget <= 0 or not blocks:
        return blocks

    indexed = list(enumerate(blocks))

    # I2.1 — Rerank: relevancia TF-IDF coseno para desempatar bajo presupuesto.
    _RERANK_W = 0.3
    _rerank_scores: dict[int, float] = {}
    if context_text and getattr(config, "STACKY_CONTEXT_RERANK_ENABLED", False):
        try:
            import math
            from collections import Counter
            from services.embeddings import _tokenize as _emb_tok

            q_tokens = _emb_tok(context_text)
            q_tf = Counter(q_tokens)
            q_norm = math.sqrt(sum(c * c for c in q_tf.values())) if q_tf else 0.0
            if q_norm > 0:
                for _idx, _block in indexed:
                    if _block_priority(_block) >= _HIGH_PRIORITY_THRESHOLD:
                        continue
                    _content = (_block.get("content") or "")
                    _b_tokens = _emb_tok(_content)
                    _b_tf = Counter(_b_tokens)
                    _b_norm = math.sqrt(sum(c * c for c in _b_tf.values())) if _b_tf else 0.0
                    if _b_norm == 0:
                        continue
                    _common = set(q_tf) & set(_b_tf)
                    _dot = sum(q_tf[t] * _b_tf[t] for t in _common)
                    _rerank_scores[_idx] = _dot / (q_norm * _b_norm)
        except Exception:  # noqa: BLE001 — best-effort
            _rerank_scores = {}

    def _sort_key(iv: tuple[int, dict]) -> tuple[float, int]:
        orig_idx, blk = iv
        prio = _block_priority(blk)
        if _rerank_scores and prio < _HIGH_PRIORITY_THRESHOLD:
            effective = prio + _RERANK_W * _rerank_scores.get(orig_idx, 0.0)
            return (-effective, orig_idx)
        return (-float(prio), orig_idx)

    # Orden de conservación: prioridad (+ rerank) desc, estable.
    ordered = sorted(indexed, key=_sort_key)

    used = 0
    kept: dict[int, dict] = {}
    dropped = 0
    truncated = 0
    for orig_idx, block in ordered:
        if not isinstance(block, dict):
            kept[orig_idx] = block
            continue
        cost = _block_token_estimate(block)
        if used + cost <= budget:
            kept[orig_idx] = block
            used += cost
            continue
        remaining = budget - used
        content = block.get("content")
        # Solo tiene sentido truncar bloques con contenido textual sustancial.
        if isinstance(content, str) and remaining > 50 and len(content) > remaining * 4:
            keep_chars = remaining * 4
            new_block = dict(block)
            new_block["content"] = content[:keep_chars].rstrip() + _TRUNCATION_MARKER
            new_block.setdefault("metadata", {})
            if isinstance(new_block.get("metadata"), dict):
                new_block["metadata"] = {**new_block["metadata"], "budget_truncated": True}
            kept[orig_idx] = new_block
            used = budget
            truncated += 1
        else:
            dropped += 1
        # A partial fill cierra el presupuesto: los siguientes (menor prioridad)
        # se descartan salvo que sean de costo nulo.
        if used >= budget:
            continue

    if dropped == 0 and truncated == 0:
        return blocks

    result = [kept[i] for i in range(len(blocks)) if i in kept]
    log(
        "info",
        f"presupuesto de contexto aplicado (F2.4): budget={budget} tok, "
        f"usados~{used}, bloques truncados={truncated}, descartados={dropped}",
    )
    return result


# ---------------------------------------------------------------------------
# Pasos individuales (cada uno best-effort)
# ---------------------------------------------------------------------------

def build_client_profile_block(
    project_name: str | None, log: LogFn | None = None
) -> dict | None:
    """Construye el bloque `client-profile` del proyecto activo (o None).

    Es el seam ÚNICO de armado del bloque: lo usan tanto el pipeline batch
    (`_inject_client_profile_block`, vía `enrich_blocks` para los runtimes
    github_copilot/codex_cli/claude_code_cli) como el flujo interactivo
    (`api/agents.open_chat`, que abre GitHub Copilot Chat y antes NO pasaba por
    `enrich_blocks` → el agente cliente-agnóstico arrancaba sin perfil). Tener un
    solo armador garantiza que el Developer reciba EXACTAMENTE el mismo perfil en
    ambos caminos.

    Garantía (plan "client profile siempre presente"): se devuelve un bloque
    SIEMPRE que haya proyecto — si el operador configuró un perfil se usa tal
    cual; si no, se cae al template default del tracker (marcado como "sin
    configurar") para que ningún agente arranque a ciegas.

    Feature flag: `STACKY_INJECT_CLIENT_PROFILE` (default `true`). Si está OFF
    devuelve None aunque haya perfil.

    Best-effort: cualquier excepción degrada en warning y devuelve None.
    """
    log = log or _noop_log
    if os.getenv("STACKY_INJECT_CLIENT_PROFILE", "true").lower() in {"0", "false", "off"}:
        return None
    if not project_name:
        return None

    try:
        from services.client_profile import (
            get_project_tracker_type,
            load_client_profile,
            merge_with_defaults,
        )

        persisted = load_client_profile(project_name)
        # "Configurado" = el operador guardó algo con contenido real. Un perfil
        # vacío (`{"schema_version": 1}`, p. ej. sembrado por un build viejo que
        # no traía templates) cuenta como NO configurado: igual lo completamos
        # con el layout estándar y lo marcamos como defaults.
        has_real_profile = isinstance(persisted, dict) and bool(
            set(persisted.keys()) - {"schema_version"}
        )
        tracker_type = get_project_tracker_type(project_name)
        # Completar SIEMPRE con el template default del tracker para que el
        # agente reciba rutas/estados/BD aunque el perfil guardado esté parcial
        # o vacío (plan 17 §3.5). `merge_with_defaults` incluye `database` —a
        # diferencia de `complete_client_profile`, usado por el editor— porque el
        # agente necesita type/dml_policy/naming (no hay secretos: el server va
        # vacío en el default y la credencial vive cifrada fuera del perfil).
        profile = merge_with_defaults(
            persisted if isinstance(persisted, dict) else {}, tracker_type
        )
        using_defaults = not has_real_profile
        if not profile:
            # Sin template default disponible: no hay nada útil que inyectar.
            return None

        # Render legible — YAML-ish para humanos, pero el contenido es plain text
        # (el LLM lo parsea como texto). Usamos json.dumps con indent porque es
        # determinístico y libre de dependencias adicionales.
        import json as _json

        terminology = profile.get("terminology") or {}
        client_label = (terminology.get("client_label") or "").strip()
        product = (terminology.get("product_name") or "").strip()
        title_suffix = ""
        if client_label or product:
            title_suffix = " — " + " · ".join([s for s in (client_label, product) if s])

        marker = " (defaults sin configurar)" if using_defaults else ""
        content = _json.dumps(profile, ensure_ascii=False, indent=2, sort_keys=True)
        if using_defaults:
            content = (
                "// NOTA: perfil no configurado por el operador. Estos son los "
                "defaults del tracker; confirmá rutas/estados antes de usarlos.\n"
                + content
            )
        # Plan 39 C2 — Inyectar directiva de acceso a BD read-only (sin password).
        # Gated por STACKY_DB_READONLY_DIRECTIVE_ENABLED (default false).
        if os.getenv("STACKY_DB_READONLY_DIRECTIVE_ENABLED", "false").lower() in {"1", "true", "on"}:
            try:
                from services.db_query import get_db_access_directive
                db_dir = get_db_access_directive(project_name)
                if db_dir.get("has_readonly"):
                    db_section = (
                        "\n\n### Acceso a base de datos (OBLIGATORIO)\n"
                        f"- Conectarse SIEMPRE con el usuario de SOLO LECTURA del perfil: "
                        f"`{db_dir['user']}` (modo {db_dir['connection_mode']}).\n"
                        f"- Servidor: `{db_dir['server']}` | Motor: `{db_dir['dialect']}`.\n"
                        "- PROHIBIDO usar autenticación integrada de Windows (`-E` / Trusted_Connection) "
                        "cuando hay usuario read-only configurado.\n"
                        "- El password NO se incluye aquí: se resuelve server-side al ejecutar la consulta."
                    )
                    content = content + db_section
            except Exception as _db_exc:  # noqa: BLE001
                log("warn", f"db_readonly_directive no disponible (continuando): {_db_exc}")

        block = {
            "kind": "text",
            "id": "client-profile",
            "title": f"Perfil del cliente: {project_name}{title_suffix}{marker}",
            "content": content,
        }
        log(
            "info",
            f"client-profile inyectado para proyecto={project_name} "
            f"(schema_version={profile.get('schema_version')}, "
            f"using_defaults={using_defaults})",
        )
        return block
    except Exception as exc:  # noqa: BLE001
        log("warn", f"client-profile no se pudo inyectar (continuando): {exc}")
        return None


def build_process_dictionary_block(client_profile: dict | None) -> dict | None:
    """Plan 42 F0 — Construye el bloque 'process-catalog' desde client_profile.

    Gated por STACKY_INJECT_PROCESS_CATALOG (default true). Función pura.
    """
    if not client_profile:
        return None
    catalog = client_profile.get("process_catalog") or []
    if not catalog:
        return None
    lines = [
        "DICCIONARIO DE PROCESOS DEL PROYECTO (fuente de verdad — NO inventes nombres ni propósitos):"
    ]
    for p in catalog:
        name = (p.get("name") or "").strip()
        purpose = (p.get("purpose") or "").strip()
        kind = (p.get("kind") or "otro").strip()
        if name and purpose:
            lines.append(f"- {name} [{kind}]: {purpose}")
    if len(lines) == 1:
        return None
    return {"id": "process-catalog", "kind": "process-catalog", "content": "\n".join(lines)}


def build_process_dictionary_block_rag(
    client_profile: dict | None,
    query: str,
    top_k: int = 8,
) -> tuple[dict, int] | None:
    """Plan 64 F2 — Bloque 'process-catalog' con solo los top-K procesos relevantes al query.

    Función PURA. Retorna (block, n_retrieved) donde n_retrieved = len(results) exacto.
    Fallback: si falla el retriever o no hay resultados → None
    (el caller usa el fallback al full-inject).
    """
    if not client_profile or not query or not query.strip():
        return None
    catalog = client_profile.get("process_catalog") or []
    if not catalog:
        return None
    try:
        from services.rag_retriever import retrieve
        index = _get_rag_index(catalog)
        results = retrieve(index, query, top_k=top_k)
        if not results:
            return None
        lines = [
            f"PROCESOS RELEVANTES AL TICKET (top-{len(results)} de {len(catalog)}, "
            f"TF-IDF — NO inventes nombres ni propósitos):"
        ]
        for chunk, score in results:
            p = chunk.payload
            name = (p.get("name") or "").strip()
            purpose = (p.get("purpose") or "").strip()
            kind = (p.get("kind") or "otro").strip()
            if name and purpose:
                lines.append(f"- {name} [{kind}]: {purpose}")
        if len(lines) == 1:
            return None
        block = {"id": "process-catalog", "kind": "process-catalog", "content": "\n".join(lines)}
        return block, len(results)  # n_retrieved exacto, no string-counted
    except Exception:  # noqa: BLE001
        return None  # degradación controlada → caller usa full-inject


# Plan 67 | 2026-06-23 | Inyecta bloque de disciplina de procesos si el flag está ON.
# Patrón idiomático del módulo: retorna list[dict]; `return blocks` en todos los fallbacks.
def _inject_process_discipline_block(
    blocks: list[dict],
    project_name: str | None,
    title: str | None,
    description: str | None,
    log: LogFn,
) -> list[dict]:
    """Si STACKY_PROCESS_DISCIPLINE_ENABLED=true y hay catálogo, decide REUSE vs CREATE y agrega bloque."""
    if not project_name or not (title or description):
        return blocks
    try:
        from services.harness_flags import get_flag
        if not get_flag("STACKY_PROCESS_DISCIPLINE_ENABLED"):
            return blocks
    except Exception:
        return blocks

    # Reusar el seam de carga de profile (Plan 42/64) — NO asumir project_ctx.process_catalog.
    try:
        from services.client_profile import load_client_profile
        profile = load_client_profile(project_name)
        if not isinstance(profile, dict):
            return blocks
        process_catalog = profile.get("process_catalog") or []
        if not process_catalog:
            return blocks
    except Exception as exc:  # noqa: BLE001
        log("warn", f"process-discipline no pudo cargar el catálogo (continuando): {exc}")
        return blocks

    try:
        decision = process_discipline.decide_process_action(
            title=title or "",
            description=description or "",
            process_catalog=process_catalog,
        )
    except Exception as exc:  # noqa: BLE001
        log("warn", f"process-discipline falló al decidir (continuando): {exc}")
        return blocks

    # [ADICIÓN ARQUITECTO] Telemetría decision.action en meta del bloque (Plan 44 observatorio).
    block = {
        "id": "process-discipline",
        "type": "process-discipline",
        "title": "Disciplina de Procesos",
        "content": process_discipline.build_discipline_block(decision),
        "meta": {
            "action": decision.action,
            "process_name": decision.process_name,
            "confidence": decision.confidence,
            "instruction_present": decision.instruction_present,
        },
    }
    log("info", f"process-discipline inyectado: action={decision.action} project={project_name}")
    return list(blocks) + [block]


def _inject_process_catalog_block(
    blocks: list[dict],
    project_name: str | None,
    log: LogFn,
    query: str | None = None,  # Plan 64 F2 — query para RAG (ticket title+description)
) -> list[dict]:
    """Plan 42 F0 + Plan 64 F2/F3 — Inyecta el bloque 'process-catalog'.

    Con STACKY_RAG_CATALOG_ENABLED=true y query disponible: recupera los top-K
    procesos más relevantes (TF-IDF puro) e incluye telemetría _rag_meta.
    Fallback: full-inject si RAG falla, está OFF, o query es vacío/None.
    Con STACKY_RAG_CATALOG_ENABLED=false (default): byte-idéntico al comportamiento anterior.
    Nota: ticket_id=None (flujo epic-from-brief sin ticket) → query=None → full-inject.
    """
    if os.getenv("STACKY_INJECT_PROCESS_CATALOG", "true").lower() in {"0", "false", "off"}:
        return blocks
    existing_ids = {b.get("id") for b in (blocks or []) if isinstance(b, dict)}
    if "process-catalog" in existing_ids:
        return blocks
    if not project_name:
        return blocks
    try:
        from services.client_profile import load_client_profile
        profile = load_client_profile(project_name)
        if not isinstance(profile, dict):
            return blocks

        rag_enabled = os.getenv("STACKY_RAG_CATALOG_ENABLED", "true").lower() in {
            "1", "true", "on"
        }
        block: dict | None = None
        _rag_meta: dict | None = None

        if rag_enabled and query and query.strip():
            top_k_raw = os.getenv("STACKY_RAG_CATALOG_TOP_K", "8")
            try:
                top_k = max(1, int(top_k_raw))
            except ValueError:
                top_k = 8
            rag_result = build_process_dictionary_block_rag(profile, query=query, top_k=top_k)
            if rag_result is not None:
                block, n_retrieved = rag_result
                catalog_size = len(profile.get("process_catalog") or [])
                log(
                    "info",
                    f"process-catalog RAG: {n_retrieved}/{catalog_size} procesos para proyecto={project_name}",
                )
                _rag_meta = {
                    "rag_enabled": True,
                    "retrieved": n_retrieved,
                    "catalog_total": catalog_size,
                    "top_k": top_k,
                }

        # Fallback: full-inject (comportamiento original)
        if block is None:
            block = build_process_dictionary_block(profile)
            if block is not None:
                log("info", f"process-catalog inyectado para proyecto={project_name}")

        if block is None:
            return blocks

        # Agregar telemetría solo cuando RAG estuvo activo (no en full-inject)
        if _rag_meta is not None:
            block = dict(block)
            block["_rag_meta"] = _rag_meta

        return list(blocks) + [block]
    except Exception as exc:  # noqa: BLE001
        log("warn", f"process-catalog no se pudo inyectar (continuando): {exc}")
        return blocks


def _inject_client_profile_block(
    blocks: list[dict], project_name: str | None, log: LogFn
) -> list[dict]:
    """Inyecta un bloque `client-profile` en `blocks`. Plan 16, Fase 2.

    Delega el armado del bloque en `build_client_profile_block` (seam único) y
    sólo agrega la deduplicación contra un bloque ya presente en la lista.
    """
    existing_ids = {b.get("id") for b in (blocks or []) if isinstance(b, dict)}
    if "client-profile" in existing_ids:
        log("info", "client-profile ya presente, omitiendo inyección")
        return blocks

    block = build_client_profile_block(project_name, log)
    if block is None:
        return blocks
    return list(blocks) + [block]


def _inject_stacky_memory_block(
    *,
    blocks: list[dict],
    project_name: str | None,
    ticket_id: int | None,
    agent_type: str,
    log: LogFn,
) -> list[dict]:
    # F2.5 — encendido por proyecto (master env + allowlist). El helper combina
    # STACKY_MEMORY_INJECTION_ENABLED con STACKY_MEMORY_INJECTION_PROJECTS.
    from services import cli_feature_flags

    if not cli_feature_flags.memory_injection_enabled(project_name):
        return blocks
    if not project_name:
        return blocks
    existing_ids = {b.get("id") for b in (blocks or []) if isinstance(b, dict)}
    if "stacky-memory" in existing_ids:
        log("info", "stacky-memory ya presente, omitiendo inyección")
        return blocks

    try:
        query_parts: list[str] = []
        ticket_title = None
        ticket_description = None
        ticket_wit = None
        with session_scope() as _mem_sess:
            ticket = _mem_sess.get(Ticket, ticket_id) if ticket_id else None
            if ticket is not None:
                ticket_title = ticket.title or ""
                ticket_description = ticket.description or ""
                ticket_wit = getattr(ticket, "work_item_type", None)
                query_parts.extend([ticket_title, ticket_description])
        query_text = "\n".join(p for p in query_parts if p).strip()

        from services import memory_store

        ctx = memory_store.get_context_for_run(
            project=project_name,
            agent_type=agent_type,
            query_text=query_text,
            inject_scopes=cli_feature_flags.memory_inject_scopes(),
            ticket_title=ticket_title,
            ticket_description=ticket_description,
            work_item_type=ticket_wit,
        )
        content = (ctx.get("content") or "").strip()
        if not content:
            return blocks
        block = {
            "kind": "text",
            "id": "stacky-memory",
            "title": f"Memoria Stacky relevante: {project_name}",
            "content": content,
            "metadata": {
                "memory_ids": ctx.get("memory_ids") or [],
                "hits": ctx.get("hits") or 0,
                "active_hits": ctx.get("active_hits") or 0,
                "suppressed_hits": ctx.get("suppressed_hits") or 0,
                # M1.2 — directivas inyectadas (claves NUEVAS, aditivas). C0.1
                # (doc 24) las lee del metadata para marcarlas locked en el preview.
                "directive_ids": ctx.get("directive_ids") or [],
                "directive_hits": ctx.get("directive_hits") or 0,
            },
        }
        log(
            "info",
            "stacky-memory inyectado "
            f"(active={ctx.get('active_hits')}, suppressed={ctx.get('suppressed_hits')})",
        )
        return [block] + list(blocks)
    except Exception as exc:  # noqa: BLE001
        log("warn", f"stacky-memory no se pudo inyectar (continuando): {exc}")
        return blocks


def _push_rejections_enabled() -> bool:
    import os
    # Default ON (Grupo B) coherente con config.STACKY_PUSH_REJECTIONS_ENABLED.
    return os.getenv("STACKY_PUSH_REJECTIONS_ENABLED", "true").lower() in {
        "1", "true", "on", "yes",
    }


def _inject_rejection_lessons(
    *, blocks: list[dict], project_name: str | None, agent_type: str, log: LogFn
) -> list[dict]:
    """Plan 48 F2 — inyecta lecciones de rechazo (operator_note) como anti-patrón.

    Detrás del flag STACKY_PUSH_REJECTIONS_ENABLED (default OFF). Dedupe cruzado
    contra los anti-patrones manuales FA-11 ya relevantes. Best-effort: ante
    cualquier fallo devuelve los blocks intactos.
    """
    if not _push_rejections_enabled():
        return blocks
    if not project_name:
        return blocks
    existing_ids = {b.get("id") for b in (blocks or []) if isinstance(b, dict)}
    if "rejection-lessons" in existing_ids:
        return blocks
    try:
        from services import rejection_lessons
        # Dedupe cruzado con anti-patrones manuales FA-11 ya relevantes.
        existing_patterns: set[str] = set()
        try:
            from services import anti_patterns
            for ap in anti_patterns.relevant(agent_type=agent_type, project=project_name):
                existing_patterns.add(" ".join((ap.pattern or "").lower().split()))
        except Exception:  # noqa: BLE001
            pass
        items = rejection_lessons.load_for_run(
            project=project_name,
            agent_type=agent_type,
            existing_patterns=existing_patterns,
        )
        if not items:
            return blocks
        prefix = rejection_lessons.build_prefix(items)
        block = {
            "kind": "text",
            "id": "rejection-lessons",
            "title": f"Lecciones de rechazos previos ({len(items)})",
            "content": prefix,
            "metadata": {"rejection_lessons_count": len(items)},
        }
        log("info", f"rejection-lessons inyectado (n={len(items)})")
        return [block] + list(blocks)
    except Exception as exc:  # noqa: BLE001
        log("warn", f"rejection-lessons no se pudo inyectar (continuando): {exc}")
        return blocks


def _inject_epic_structured(
    ticket_id: int | None, agent_type: str, blocks: list[dict], log: LogFn
) -> list[dict]:
    """Inyecta ado-epic-structured cuando el agente es functional y el ticket es Epic."""
    with session_scope() as _epic_sess:
        _epic_ticket = _epic_sess.get(Ticket, ticket_id) if ticket_id else None
        _is_epic = (
            _epic_ticket is not None
            and agent_type == "functional"
            and (_epic_ticket.work_item_type or "").strip().lower() == "epic"
        )
        if not _is_epic:
            return blocks
        _existing_ids = {b.get("id") for b in (blocks or []) if isinstance(b, dict)}
        if "ado-epic-structured" in _existing_ids:
            log("info", "ado-epic-structured ya presente, omitiendo inyección")
            return blocks
        _epic_block: dict = {
            "kind": "text",
            "id": "ado-epic-structured",
            "title": f"Epic ADO-{_epic_ticket.ado_id}: {_epic_ticket.title}",
            "content": (
                f"epic_id: {_epic_ticket.ado_id}\n"
                f"epic_ado_id: {_epic_ticket.ado_id}\n"
                f"epic_output_dir: Agentes/outputs/epic-{_epic_ticket.ado_id}\n"
                "epic_id_rule: epic_id/epic_ado_id es el System.Id real de Azure DevOps; "
                "no uses etiquetas humanas del título como EP-26, EP-28, etc. como id.\n"
                f"epic_title: {_epic_ticket.title}\n"
                f"epic_description:\n{_epic_ticket.description or ''}"
            ),
        }
        log("info", f"ado-epic-structured inyectado para Epic ADO-{_epic_ticket.ado_id}")
        return list(blocks) + [_epic_block]


def _inject_artifact_context(
    ticket_id: int | None, blocks: list[dict], log: LogFn
) -> list[dict]:
    """Inyecta filesystem-artifacts-status (comment.html / pending-task.json existentes)."""
    try:
        from services import artifact_context

        with session_scope() as _art_sess:
            _art_ticket = _art_sess.get(Ticket, ticket_id) if ticket_id else None
            _art_ado_id = _art_ticket.ado_id if _art_ticket else None
            _art_type = _art_ticket.work_item_type if _art_ticket else None
            _exec_rows = (
                _art_sess.query(AgentExecution.id)
                .filter(AgentExecution.ticket_id == ticket_id)
                .order_by(AgentExecution.id.desc())
                .limit(10)
                .all()
                if ticket_id
                else []
            )
            _exec_ids = [r[0] for r in _exec_rows]
        blocks, _art_info = artifact_context.inject_into_blocks(
            blocks,
            ado_id=_art_ado_id,
            work_item_type=_art_type,
            execution_ids=_exec_ids,
        )
        if _art_info and _art_info.get("injected"):
            log(
                "info",
                "filesystem-artifacts-status inyectado "
                f"(pending={_art_info.get('pending_count')}, "
                f"consumed={_art_info.get('consumed_count')}, "
                f"comment_html={_art_info.get('has_comment_html')})",
            )
    except Exception as _exc_art:  # noqa: BLE001
        log("warn", f"artifact_context falló (continuando sin bloque): {_exc_art}")
    return blocks


def _inject_similar_tickets(
    ticket_id: int | None,
    agent_type: str,
    ticket_ado_id: int | None,
    blocks: list[dict],
    project_name: str | None,
    log: LogFn,
) -> list[dict]:
    """Inyecta ado-similar-tickets para que el agente no proponga duplicados."""
    if (
        os.getenv("STACKY_SIMILAR_TICKETS_ENABLED", "true").lower() == "false"
        or agent_type not in {"functional", "technical"}
        or ticket_ado_id is None
    ):
        return blocks
    try:
        from config import config as _cfg
        from services import similar_tickets

        with session_scope() as _sim_sess:
            _sim_ticket = _sim_sess.get(Ticket, ticket_id) if ticket_id else None
            _sim_title = _sim_ticket.title if _sim_ticket else ""
            _sim_project = _sim_ticket.project if _sim_ticket else "Strategist_Pacifico"

        # I3.2 — Cache de lecturas ADO
        _ttl = int(getattr(_cfg, "STACKY_ADO_READ_CACHE_TTL_SEC", 0))
        if _ttl > 0:
            from services.ado_read_cache import _singleton as _ado_cache
            _cache_key = (project_name or "", str(ticket_ado_id), "similar")

            def _fetch_sim():
                return similar_tickets.inject_into_blocks(
                    [],
                    current_ado_id=ticket_ado_id,
                    current_title=_sim_title,
                    project=_sim_project or "Strategist_Pacifico",
                    project_name=project_name,
                )

            _added, _sim_info = _ado_cache.get_or_fetch(_cache_key, _fetch_sim, _ttl)
            _existing_ids = {b.get("id") for b in blocks if isinstance(b, dict) and b.get("id")}
            blocks = list(blocks) + [
                b for b in (_added or [])
                if isinstance(b, dict) and b.get("id") not in _existing_ids
            ]
        else:
            blocks, _sim_info = similar_tickets.inject_into_blocks(
                blocks,
                current_ado_id=ticket_ado_id,
                current_title=_sim_title,
                project=_sim_project or "Strategist_Pacifico",
                project_name=project_name,
            )

        if _sim_info and _sim_info.get("injected"):
            log("info", f"ado-similar-tickets inyectado (count={_sim_info.get('count')})")
    except Exception as _exc_sim:  # noqa: BLE001
        log("warn", f"similar_tickets falló (continuando sin bloque): {_exc_sim}")
    return blocks


def build_ticket_context_text(
    *,
    ado_id: int | None,
    title: str | None,
    description: str | None,
    work_item_type: str | None,
    blocks: list[dict] | None,
) -> str:
    """Arma el texto legible de "## Ticket y contexto" para los runtimes CLI.

    Incluye el encabezado del ticket (ADO-id, tipo, título, descripción) y un
    render de los context_blocks enriquecidos (épica, comentarios ADO, tickets
    similares, "Mensaje adicional" del modal, nota del operador, etc.).

    Reemplaza el `ticket_message = ticket.title` que dejaba al agente arrancar a
    ciegas: ahora recibe lo mismo que recibiría el flujo github_copilot.
    """
    parts: list[str] = []

    header = f"ADO-{ado_id}" if ado_id is not None else "(ticket sin ADO id)"
    if work_item_type:
        header += f" · {work_item_type}"
    parts.append(f"**Ticket:** {header}")
    if title:
        parts.append(f"**Título:** {title}")
    if description and description.strip():
        parts.append(f"**Descripción:**\n{description.strip()}")

    rendered_blocks = _render_blocks(blocks)
    if rendered_blocks:
        parts.append("### Contexto adicional\n\n" + rendered_blocks)

    return "\n\n".join(parts).strip()


def _render_blocks(blocks: list[dict] | None) -> str:
    """Render legible de los context_blocks (mismo criterio de selección que el
    context_text de github_copilot, pero con encabezados por bloque)."""
    sections: list[str] = []
    for b in blocks or []:
        if not isinstance(b, dict):
            continue
        title = (b.get("title") or "").strip()
        lines: list[str] = []
        content = b.get("content")
        if isinstance(content, str) and content.strip():
            lines.append(content.strip())
        for it in b.get("items") or []:
            if isinstance(it, dict) and it.get("selected"):
                label = (it.get("label") or "").strip()
                if label:
                    lines.append(f"- {label}")
        body = "\n".join(lines).strip()
        if not title and not body:
            continue
        if title and body:
            sections.append(f"#### {title}\n{body}")
        elif title:
            sections.append(f"#### {title}")
        else:
            sections.append(body)
    return "\n\n".join(sections).strip()


def _inject_ado_context(
    *,
    ticket_id: int | None,
    agent_type: str,
    ticket_ado_id: int | None,
    blocks: list[dict],
    project: str | None,
    project_ctx: Any,
    project_name: str | None,
    ticket_obj: Any,
    log: LogFn,
) -> tuple[list[dict], dict | None]:
    """Inyecta comentarios/adjuntos de ADO. Devuelve (blocks, stats)."""
    if ticket_ado_id is None:
        return blocks, None
    try:
        from config import config as _cfg
        from services import ado_context

        # I3.2 — Cache de lecturas ADO
        _ttl = int(getattr(_cfg, "STACKY_ADO_READ_CACHE_TTL_SEC", 0))
        _tracker_proj = project_ctx.tracker_project if project_ctx else project

        if _ttl > 0:
            from services.ado_read_cache import _singleton as _ado_cache
            _cache_key = (project_name or "", str(ticket_ado_id), "ado_context")

            def _fetch_ado():
                return ado_context.enrich(
                    ticket_id=ticket_id,
                    agent_type=agent_type,
                    existing_blocks=[],
                    ado_id=ticket_ado_id,
                    project_name=project_name,
                    tracker_project=_tracker_proj,
                    ticket=ticket_obj,
                    log=log,
                    return_stats=True,
                )

            _added, stats = _ado_cache.get_or_fetch(_cache_key, _fetch_ado, _ttl)
            _existing_ids = {b.get("id") for b in blocks if isinstance(b, dict) and b.get("id")}
            blocks = list(blocks) + [
                b for b in (_added or [])
                if isinstance(b, dict) and b.get("id") not in _existing_ids
            ]
            return blocks, stats
        else:
            blocks, stats = ado_context.enrich(
                ticket_id=ticket_id,
                agent_type=agent_type,
                existing_blocks=blocks or [],
                ado_id=ticket_ado_id,
                project_name=project_name,
                tracker_project=_tracker_proj,
                ticket=ticket_obj,
                log=log,
                return_stats=True,
            )
            return blocks, stats
    except Exception as _exc_ado:  # noqa: BLE001
        log("warn", f"ado_context enrich falló (continuando sin enrichment): {_exc_ado}")
        return blocks, {"error": str(_exc_ado)}


# ---------------------------------------------------------------------------
# Q0.1 — Inyección de criterios de aceptación como checklist
# ---------------------------------------------------------------------------

def _acceptance_criteria_enabled(project_name: str | None) -> bool:
    from config import config
    if not getattr(config, "STACKY_ACCEPTANCE_CRITERIA_INJECTION_ENABLED", False):
        return False
    projects_csv: str = getattr(config, "STACKY_ACCEPTANCE_CRITERIA_PROJECTS", "") or ""
    if projects_csv.strip():
        allowed = {p.strip().lower() for p in projects_csv.split(",") if p.strip()}
        if project_name and project_name.lower() not in allowed:
            return False
    return True


def _inject_acceptance_criteria(
    *,
    ticket_id: int | None,
    project_name: str | None,
    blocks: list[dict],
    log: LogFn,
) -> list[dict]:
    """Q0.1 — Inyecta acceptance criteria del ticket como checklist obligatorio.

    Bloque id='acceptance-criteria', prioridad 74 (alta, nunca podado).
    Best-effort; si no hay AC o ADO falla, devuelve los bloques sin tocar.
    Participa del dedup I0.1 (sin inyección duplicada con ado-epic-structured).
    """
    if not _acceptance_criteria_enabled(project_name):
        return blocks
    if not ticket_id:
        return blocks

    existing_ids = {b.get("id") for b in blocks if isinstance(b, dict)}
    if "acceptance-criteria" in existing_ids:
        log("info", "acceptance-criteria ya presente, omitiendo inyección")
        return blocks

    try:
        from db import session_scope as _ss
        from models import Ticket as _Ticket
        from services.acceptance_criteria import render_checklist, resolve

        with _ss() as _ses:
            ticket = _ses.get(_Ticket, ticket_id)
            if ticket is None:
                return blocks
            # Snapshot de escalares para usar fuera de sesión
            _ticket_snap = ticket

        ac_text = resolve(_ticket_snap)
        if not ac_text:
            return blocks

        checklist = render_checklist(ac_text)
        if not checklist:
            return blocks

        block = {
            "kind": "text",
            "id": "acceptance-criteria",
            "title": "Criterios de aceptación (obligatorios)",
            "content": checklist,
        }
        log("info", "acceptance-criteria inyectado como checklist")
        return list(blocks) + [block]
    except Exception as exc:  # noqa: BLE001
        log("warn", f"acceptance-criteria no se pudo inyectar (continuando): {exc}")
        return blocks


# ---------------------------------------------------------------------------
# A1.1 — Inyección del blanco del contrato de aceptación ejecutable
# ---------------------------------------------------------------------------


def _inject_acceptance_contract_block(
    *,
    ticket_id: int | None,
    project_name: str | None,
    blocks: list[dict],
    log: LogFn,
) -> list[dict]:
    """A1.1 — Inyecta el blanco del contrato de aceptación como bloque de alta prioridad.

    Solo actúa cuando:
    - STACKY_ACCEPTANCE_CONTRACT_ENABLED=true
    - STACKY_ACCEPTANCE_CONTRACT_MODE=gate
    - El contrato pre-derivado existe en el contexto de la ejecución actual (metadata)
    - El contrato no es n/a y tiene checks_kept

    El bloque tiene prioridad HIGH y no es podado (como acceptance-criteria).
    Best-effort; si el contrato no está disponible, no inyecta nada.
    """
    try:
        from config import config as _cfg
        if not getattr(_cfg, "STACKY_ACCEPTANCE_CONTRACT_ENABLED", False):
            return blocks
        mode = getattr(_cfg, "STACKY_ACCEPTANCE_CONTRACT_MODE", "off")
        if mode != "gate":
            return blocks
    except Exception:
        return blocks

    if not ticket_id:
        return blocks

    # Verificar que no esté ya inyectado
    existing_ids = {b.get("id") for b in blocks if isinstance(b, dict)}
    if "acceptance-contract" in existing_ids:
        return blocks

    # El contrato se almacena en el contexto de ejecución actual si ya fue derivado.
    # Para no re-derivar acá, intentamos leerlo de la ejecución activa.
    # Si no está disponible → no inyectar (best-effort, no bloquea el run).
    try:
        from db import session_scope as _ss
        from models import AgentExecution as _AE
        from sqlalchemy import desc

        with _ss() as _ses:
            # Buscar la ejecución más reciente del ticket con acceptance_contract
            rows = (
                _ses.query(_AE)
                .filter(_AE.ticket_id == ticket_id)
                .order_by(desc(_AE.started_at))
                .limit(3)
                .all()
            )
            contract_data = None
            for row in rows:
                md = row.metadata_dict
                ac = md.get("acceptance_contract")
                if isinstance(ac, dict) and not ac.get("n_a") and ac.get("checks_kept"):
                    contract_data = ac
                    break

        if not contract_data:
            return blocks

        checks_kept = contract_data.get("checks_kept") or []
        if not checks_kept:
            return blocks

        lines = ["Tu entregable DEBE pasar estos chequeos ejecutables:"]
        for i, ch in enumerate(checks_kept, 1):
            lines.append(f"{i}. [{ch.get('kind', 'command')}] {ch.get('ticket_clause', '')}")
        lines.append("Trabajá hasta que todos pasen.")

        block = {
            "kind": "text",
            "id": "acceptance-contract",
            "priority": "high",
            "title": "Contrato de aceptación ejecutable (obligatorio)",
            "content": "\n".join(lines),
        }
        log("info", f"acceptance-contract inyectado ({len(checks_kept)} chequeo(s))")
        return list(blocks) + [block]

    except Exception as exc:  # noqa: BLE001
        log("warn", f"acceptance-contract no se pudo inyectar (continuando): {exc}")
        return blocks


# ---------------------------------------------------------------------------
# Q1.2 — Inyección de few-shot de outputs aprobados (runtimes CLI)
# ---------------------------------------------------------------------------

def _cli_fewshot_enabled(project_name: str | None) -> bool:
    from config import config
    if not getattr(config, "STACKY_CLI_FEWSHOT_ENABLED", False):
        return False
    projects_csv: str = getattr(config, "STACKY_CLI_FEWSHOT_PROJECTS", "") or ""
    if projects_csv.strip():
        allowed = {p.strip().lower() for p in projects_csv.split(",") if p.strip()}
        if project_name and project_name.lower() not in allowed:
            return False
    return True


def _inject_cli_fewshot(
    *,
    ticket_id: int | None,
    agent_type: str,
    project_name: str | None,
    blocks: list[dict],
    log: LogFn,
) -> list[dict]:
    """Q1.2 — Inyecta ejemplos de outputs aprobados (few-shot) para runtimes CLI.

    Bloque id='few-shot-approved', prioridad 55 (podable bajo presión de budget).
    No duplica el path copilot (agents/base.py:70-88).
    Si no hay aprobados: no-op silencioso.
    """
    if not _cli_fewshot_enabled(project_name):
        return blocks

    existing_ids = {b.get("id") for b in blocks if isinstance(b, dict)}
    if "few-shot-approved" in existing_ids:
        log("info", "few-shot-approved ya presente, omitiendo inyección")
        return blocks

    try:
        from config import config
        from services.few_shot import build_prefix, pick_examples

        k = int(getattr(config, "STACKY_CLI_FEWSHOT_K", 2))
        examples = pick_examples(
            agent_type=agent_type,
            project=project_name,
            exclude_ticket_id=ticket_id,
            k=k,
            max_chars_per_example=6000,
        )
        if not examples:
            return blocks

        prefix = build_prefix(examples)
        if not prefix:
            return blocks

        block = {
            "kind": "text",
            "id": "few-shot-approved",
            "title": f"Ejemplos de outputs aprobados ({len(examples)})",
            "content": prefix,
        }
        log("info", f"few-shot-approved inyectado (k={len(examples)})")
        return list(blocks) + [block]
    except Exception as exc:  # noqa: BLE001
        log("warn", f"few-shot-approved no se pudo inyectar (continuando): {exc}")
        return blocks
