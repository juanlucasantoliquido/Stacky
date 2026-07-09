"""services/environment_remote.py — Plan 108 F5.

Plan/apply de Ambientes (Plan 89/107) contra el servidor REMOTO seleccionado
(cierra RC3: hoy `environment_init.py` evalúa y crea siempre en el filesystem
local del backend). Reusa el riel WinRM auditado del Plan 105
(services/remote_exec.run_remote) — NUNCA reinventa transporte, credenciales
ni auditoría.

Todas las funciones son PURAS salvo `plan_environment_remote` y
`apply_environment_remote`, que llaman `run_remote` (I/O de red vía WinRM).

Shape de salida con PARIDAD EXACTA de keys contra el plan/apply local
(services/environment_init.py) + {'remote': True, 'server_alias': alias} —
DirTreePreview (Plan 107) y el handshake de fingerprint del apply consumen
ese shape sin distinguir local/remoto.
"""
from __future__ import annotations

import ntpath

_CHUNK = 50       # paths por comando remoto (límite de longitud de línea WinRM)
_MAX_CHUNKS = 20  # (C7 v2) tope duro: 20*50 = 1000 paths ⇒ nunca un request de minutos


def _q(path: str) -> str:
    """Escapa comillas simples PowerShell: ' -> ''. Retorna 'path' entre comillas simples."""
    return "'" + str(path).replace("'", "''") + "'"


def build_remote_status_command(abs_paths: list[str]) -> str:
    """Por cada path emite DOS statements Test-Path separados por ';' (existencia +
    directorio). SIN llaves ni loops (el validador read-only rechaza '{'/'}',
    services/remote_exec.py:52-56). El comando resultante DEBE pasar
    is_read_only_command()."""
    stmts: list[str] = []
    for p in abs_paths:
        q = _q(p)
        stmts.append(f"Test-Path -LiteralPath {q}")
        stmts.append(f"Test-Path -LiteralPath {q} -PathType Container")
    return ";".join(stmts)


def parse_status_output(stdout: str, abs_paths: list[str]) -> list[dict]:
    """stdout = líneas True/False en pares por path (en el mismo orden de
    abs_paths). Retorna [{'path': p, 'exists': bool, 'is_dir': bool}]. Si el
    número de líneas no es 2*len(abs_paths) ⇒ ValueError('remote_status_parse_error')
    (nunca inventa estados ante output corrupto/desalineado)."""
    lines = [ln.strip() for ln in (stdout or "").splitlines() if ln.strip()]
    if len(lines) != 2 * len(abs_paths):
        raise ValueError("remote_status_parse_error")
    out: list[dict] = []
    for i, p in enumerate(abs_paths):
        exists = lines[2 * i].lower() == "true"
        is_dir = lines[2 * i + 1].lower() == "true"
        out.append({"path": p, "exists": exists, "is_dir": is_dir})
    return out


def build_remote_mkdir_command(abs_paths: list[str]) -> str:
    """'New-Item -ItemType Directory -Force -LiteralPath <p> | Out-Null' unidos por ';'.
    -Force lo vuelve idempotente (no falla si el directorio ya existe)."""
    return ";".join(
        f"New-Item -ItemType Directory -Force -LiteralPath {_q(p)} | Out-Null"
        for p in abs_paths
    )


def resolve_remote_layout(
    root: str, rel_paths: list[str]
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """PURA, con ntpath (el server destino es Windows; run_remote es win-only,
    services/remote_exec.py:193). Por cada rel: final = ntpath.normpath(ntpath.join(root, rel)).
    unsafe con reason (C2 v2, paridad de espíritu con el guard local
    environment_init.plan_environment, sin realpath porque no hay fs local que resolver):
      - 'path_demasiado_largo' si len(final) > 240 (mismo umbral que el local, chequeado
        PRIMERO, igual orden que environment_init.plan_environment).
      - 'fuera_de_root' si el final no queda BAJO root (comparación textual
        case-insensitive con ntpath.normcase + frontera de separador — nunca un
        prefijo de string crudo, ej. 'Prod-evil' NO matchea 'Prod').
    Retorna ([(rel, final_abs)] seguros, [(rel, reason)] unsafe)."""
    norm_root = ntpath.normcase(ntpath.normpath(root))
    safe: list[tuple[str, str]] = []
    unsafe: list[tuple[str, str]] = []
    for rel in rel_paths:
        final = ntpath.normpath(ntpath.join(root, rel))
        if len(final) > 240:
            unsafe.append((rel, "path_demasiado_largo"))
            continue
        nf = ntpath.normcase(final)
        if nf == norm_root or nf.startswith(norm_root + "\\"):
            safe.append((rel, final))
        else:
            unsafe.append((rel, "fuera_de_root"))
    return safe, unsafe


def plan_environment_remote(
    alias: str, root: str, rel_paths: list[str],
    *, conversation_id: int | None = None, user: str = "",
) -> dict:
    """SOLO LECTURA remota. Shape con paridad EXACTA de keys contra el plan
    local (environment_init.plan_environment) + {'remote': True, 'server_alias'}."""
    from services.remote_exec import run_remote, is_read_only_command
    from services.environment_init import layout_fingerprint

    safe, unsafe_layout = resolve_remote_layout(root, rel_paths)

    # (C4 v2) Pre-validar CADA path seguro contra el blocklist read-only: un path
    # cuyo TEXTO dispara el blocklist (p.ej. contiene "New-", "del", "&", "curl")
    # se marca unsafe y NUNCA viaja al servidor — jamás tumba el plan entero.
    verified_safe: list[tuple[str, str]] = []
    unsafe_blocked: list[tuple[str, str]] = []
    for rel, final in safe:
        probe_cmd = build_remote_status_command([final])
        if is_read_only_command(probe_cmd):
            verified_safe.append((rel, final))
        else:
            unsafe_blocked.append((rel, "path_no_verificable_remoto"))

    all_unsafe = unsafe_layout + unsafe_blocked

    # (C7 v2) Tope duro de chunks: nunca un request HTTP de minutos.
    n_chunks = (len(verified_safe) + _CHUNK - 1) // _CHUNK if verified_safe else 0
    if n_chunks > _MAX_CHUNKS:
        return {"ok": False, "error": "remote_plan_too_large", "remote": True}

    # Probe del root primero.
    root_result = run_remote(
        alias, build_remote_status_command([root]), mode="read_only",
        conversation_id=conversation_id, user=user, timeout_s=30,
    )
    if not root_result["ok"]:
        return {"ok": False, "error": root_result["error"], "remote": True}
    root_exists = parse_status_output(root_result["stdout"], [root])[0]["is_dir"]

    # Probes de los restantes en chunks.
    statuses: dict[str, dict] = {}
    for i in range(0, len(verified_safe), _CHUNK):
        chunk = verified_safe[i:i + _CHUNK]
        finals = [f for _, f in chunk]
        result = run_remote(
            alias, build_remote_status_command(finals), mode="read_only",
            conversation_id=conversation_id, user=user, timeout_s=30,
        )
        if not result["ok"]:
            return {"ok": False, "error": result["error"], "remote": True}
        for parsed in parse_status_output(result["stdout"], finals):
            statuses[parsed["path"]] = parsed

    entries: list[dict] = []
    summary = {"to_create": 0, "exists_ok": 0, "conflict": 0, "unsafe": 0}
    for rel, final in verified_safe:
        st = statuses.get(final)
        if st is None:
            status, reason = "unsafe", "remote_status_parse_error"
        elif not st["exists"]:
            status, reason = "to_create", None
        elif st["is_dir"]:
            status, reason = "exists_ok", None
        else:
            status, reason = "conflict", None
        summary[status] += 1
        entries.append({"path": rel, "status": status, "reason": reason})
    for rel, reason in all_unsafe:
        summary["unsafe"] += 1
        entries.append({"path": rel, "status": "unsafe", "reason": reason})

    return {
        "root": root,
        "root_exists": root_exists,
        "layout_fingerprint": layout_fingerprint(root, rel_paths),
        "entries": entries,
        "summary": summary,
        "remote": True,
        "server_alias": alias,
    }


def apply_environment_remote(
    alias: str, root: str, approved: list[tuple[str, str]],
    *, conversation_id: int | None = None, user: str = "",
) -> dict:
    """approved = pares (rel, final_abs) salidos de resolve_remote_layout (C2 v2 —
    se necesita rel para reportar con paridad). Re-planifica server-side PRIMERO
    (paridad con el local, que re-planifica en environment_init.py:213 — la
    clasificación NUNCA sale de la lista del cliente), mkdir SOLO los to_create
    en chunks vía run_remote(mode='write') y verifica con los mismos probes
    read_only. NUNCA borra nada. Shape con paridad EXACTA del apply local
    (environment_init.py:235-241) + {'remote': True}."""
    from services.remote_exec import run_remote

    if not approved:
        return {"created": [], "skipped_existing": [], "conflicts": [], "unsafe": [],
                "failed": [], "remote": True}

    rel_paths = [rel for rel, _ in approved]
    final_by_rel = dict(approved)

    plan = plan_environment_remote(alias, root, rel_paths, conversation_id=conversation_id, user=user)
    if plan.get("ok") is False:
        return {"ok": False, "error": plan.get("error"), "remote": True}

    created: list[str] = []
    skipped_existing: list[str] = []
    conflicts: list[str] = []
    unsafe: list[str] = []
    failed: list[dict] = []
    to_create: list[tuple[str, str]] = []

    for entry in plan["entries"]:
        rel, status = entry["path"], entry["status"]
        if status == "exists_ok":
            skipped_existing.append(rel)
        elif status == "conflict":
            conflicts.append(rel)
        elif status == "unsafe":
            unsafe.append(rel)
        elif status == "to_create":
            final = final_by_rel.get(rel)
            if final:
                to_create.append((rel, final))

    if not to_create:
        return {"created": created, "skipped_existing": skipped_existing,
                "conflicts": conflicts, "unsafe": unsafe, "failed": failed, "remote": True}

    for i in range(0, len(to_create), _CHUNK):
        chunk = to_create[i:i + _CHUNK]
        finals = [f for _, f in chunk]

        mk_result = run_remote(
            alias, build_remote_mkdir_command(finals), mode="write",
            conversation_id=conversation_id, user=user, timeout_s=30,
        )
        if not mk_result["ok"]:
            for rel, _final in chunk:
                failed.append({"path": rel, "error": mk_result.get("error") or "remote_mkdir_failed"})
            continue

        # Verificación posterior (read_only) — NUNCA confía ciegamente en el exit code.
        verify_result = run_remote(
            alias, build_remote_status_command(finals), mode="read_only",
            conversation_id=conversation_id, user=user, timeout_s=30,
        )
        if not verify_result["ok"]:
            for rel, _final in chunk:
                failed.append({"path": rel, "error": verify_result.get("error") or "remote_verify_failed"})
            continue

        parsed_by_final = {p["path"]: p for p in parse_status_output(verify_result["stdout"], finals)}
        for rel, final in chunk:
            st = parsed_by_final.get(final)
            if st and st["is_dir"]:
                created.append(rel)
            else:
                failed.append({"path": rel, "error": "remote_mkdir_not_verified"})

    return {
        "created": created,
        "skipped_existing": skipped_existing,
        "conflicts": conflicts,
        "unsafe": unsafe,
        "failed": failed,
        "remote": True,
    }
