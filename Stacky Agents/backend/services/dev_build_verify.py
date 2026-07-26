"""Plan 210 — Gate de build determinista del Developer.

Hoy el "Build OK" del Developer es prosa: el LLM lo escribe y esa narración
dispara la transición del ticket. Acá el hecho lo produce la MÁQUINA: se resuelve
la entrada canónica de build (prefiere `.sln`), se invoca el builder real del
Taller de Compilación y se persiste un veredicto tipado.

Reglas duras:
  - La **ausencia** de veredicto es "no verificado", JAMÁS "OK".
  - Un veredicto de otra corrida tampoco vale: está ligado a `execution_id`.
  - Sin `.sln`, sin toolchain o con build fallido, el veredicto nunca es `gate_ok`.

Núcleo determinista: cero LLM, cero red.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Conjunto CONGELADO de razones (parte del contrato que consume el Plan 211).
_REASONS = ("ok", "no_sln", "csproj_not_allowed", "csproj_entry", "build_failed",
            "toolchain_missing", "build_workshop_unavailable", "workspace_missing",
            "stale_verdict", "not_verified")

_POLL_INTERVAL_SEC = 2
_VERIFY_POLL_TIMEOUT_SEC = 1800
_TERMINAL = {"success", "failed", "cancelled", "toolchain_missing"}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z"


@dataclass(frozen=True)
class BuildVerdict:
    ok: bool = False
    gate_ok: bool = False
    entry_kind: str = "none"          # "sln" | "csproj" | "none"
    solution: str = ""
    solutions: tuple = ()
    returncode: int = -1
    summary_path: str = ""
    reason: str = "not_verified"
    toolchain: dict = field(
        default_factory=lambda: {"available": False, "builder": None, "version": None}
    )
    build_id: str = ""
    verified_at: str = ""
    # Liga el veredicto a la corrida: un verde de una corrida ANTERIOR no vale
    # como verde de la actual (fin del falso verde por staleness).
    execution_id: int = 0
    blocking_findings: tuple = ()
    warnings: tuple = ()


def _not_verified(reason: str, *, entry_kind: str = "none", solutions: tuple = (),
                  toolchain: dict | None = None, verified_at: str | None = None,
                  execution_id: int = 0) -> "BuildVerdict":
    return BuildVerdict(
        ok=False, gate_ok=False, entry_kind=entry_kind, solution="",
        solutions=tuple(solutions), returncode=-1, summary_path="",
        reason=(reason if reason in _REASONS else "not_verified"),
        toolchain=toolchain or {"available": False, "builder": None, "version": None},
        build_id="", verified_at=(verified_at or _utcnow_iso()),
        execution_id=execution_id, blocking_findings=(), warnings=(),
    )


# ── F1 — resolución determinista de la entrada de build ──────────────────────

def resolve_build_entry(profile: dict, workspace_root) -> dict:
    """`{"entry_kind", "solutions", "reason"}`. Pura salvo el acceso al disco.

    Prefiere el `.sln` declarado en el perfil; si no hay, escanea. Un `.csproj`
    suelto NO cuenta como entrada verificable salvo que el perfil lo permita.
    """
    if not workspace_root or not os.path.isdir(str(workspace_root)):
        return {"entry_kind": "none", "solutions": [], "reason": "workspace_missing"}

    build_cfg = (profile or {}).get("build") or {}
    declarados = build_cfg.get("online_solutions") or []
    resueltos: list = []
    for entrada in declarados:
        if not isinstance(entrada, str) or not entrada.strip():
            continue
        ruta = entrada if os.path.isabs(entrada) else os.path.join(str(workspace_root), entrada)
        ruta = os.path.normpath(ruta)
        if ruta.lower().endswith(".sln") and os.path.exists(ruta):
            resueltos.append(ruta)
    if resueltos:
        return {"entry_kind": "sln", "solutions": sorted(set(resueltos)), "reason": "ok"}

    encontrados: list = []
    proyectos: list = []
    try:
        from services.solution_scanner import scan_solutions_ex

        catalogo = scan_solutions_ex(str(workspace_root))
        for sol in catalogo.get("solutions", []):
            encontrados.append(sol["sln_path"])
            proyectos.extend(p.get("csproj_path") for p in sol.get("projects", []) or [])
    except ImportError:
        logger.debug("el Taller de Compilación no está disponible; sin escaneo")

    if encontrados:
        return {"entry_kind": "sln", "solutions": sorted(set(encontrados)), "reason": "ok"}

    if not proyectos:
        proyectos = _scan_csproj(str(workspace_root))

    if proyectos:
        if bool(build_cfg.get("allow_csproj_entry", False)):
            return {"entry_kind": "csproj", "solutions": sorted(set(p for p in proyectos if p)),
                    "reason": "csproj_entry"}
        return {"entry_kind": "none", "solutions": [], "reason": "csproj_not_allowed"}

    return {"entry_kind": "none", "solutions": [], "reason": "no_sln"}


_IGNORE_DIRS = ("node_modules", ".git", "venv", ".venv", "bin", "obj",
                "__pycache__", "packages", ".vs", "dist")
_CSPROJ_MAX_DEPTH = 8


def _scan_csproj(root: str) -> list:
    """Fallback acotado si el scanner del Taller no está. Nunca lanza."""
    out: list = []
    try:
        base = os.path.normpath(root)
        for dirpath, dirnames, filenames in os.walk(base):
            if dirpath[len(base):].count(os.sep) >= _CSPROJ_MAX_DEPTH:
                dirnames[:] = []
            dirnames[:] = [d for d in dirnames if d not in _IGNORE_DIRS]
            for fname in filenames:
                if fname.lower().endswith((".csproj", ".vbproj")):
                    out.append(os.path.join(dirpath, fname))
    except OSError:
        logger.debug("escaneo de .csproj falló (no crítico)", exc_info=True)
    return out


# ── F2 — veredicto: persistencia + build real ────────────────────────────────

def verdict_path(ado_id: int, workspace_root) -> Path:
    if workspace_root:
        return Path(str(workspace_root)) / "Agentes" / "outputs" / str(ado_id) / "build.verdict.json"
    from runtime_paths import data_dir

    return data_dir() / "dev_build_verdicts" / f"{ado_id}.json"


def write_verdict(ado_id: int, workspace_root, verdict: BuildVerdict) -> None:
    """Best-effort: si no se puede escribir, se loguea y se sigue."""
    try:
        path = verdict_path(ado_id, workspace_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(verdict), indent=2, ensure_ascii=False),
                        encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        logger.warning("no se pudo persistir el veredicto de build", exc_info=True)


def read_verdict(ado_id: int, workspace_root):
    """Veredicto persistido, o None (que el caller trata como 'no verificado')."""
    try:
        path = verdict_path(ado_id, workspace_root)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        # json.load devuelve listas; el dataclass frozen espera tuplas.
        return BuildVerdict(
            ok=bool(data.get("ok")),
            gate_ok=bool(data.get("gate_ok")),
            entry_kind=str(data.get("entry_kind") or "none"),
            solution=str(data.get("solution") or ""),
            solutions=tuple(data.get("solutions") or ()),
            returncode=int(data.get("returncode", -1)),
            summary_path=str(data.get("summary_path") or ""),
            reason=str(data.get("reason") or "not_verified"),
            toolchain=data.get("toolchain") or {"available": False, "builder": None,
                                                "version": None},
            build_id=str(data.get("build_id") or ""),
            verified_at=str(data.get("verified_at") or ""),
            execution_id=int(data.get("execution_id") or 0),
            blocking_findings=tuple(data.get("blocking_findings") or ()),
            warnings=tuple(data.get("warnings") or ()),
        )
    except Exception:  # noqa: BLE001
        logger.debug("veredicto de build ilegible", exc_info=True)
        return None


def _detect_toolchain_safe() -> dict:
    try:
        from services.build_toolchain import detect_toolchain

        return detect_toolchain()
    except Exception:  # noqa: BLE001
        return {"available": False, "builder": None, "version": None, "remediation": None}


def _poll_until_terminal(builder, build_id) -> dict:
    """Sobre `{status, summary}`. SIEMPRE dict, nunca None.

    Se itera sobre el `status` TOP-LEVEL del sobre (el `summary` es null mientras
    corre). Un `get_status` que devuelve None 5 veces seguidas = build perdido.
    Timeout ⇒ `failed` sintético: jamás "ok".
    """
    deadline = time.monotonic() + _VERIFY_POLL_TIMEOUT_SEC
    none_streak = 0
    while True:
        env = builder.get_status(build_id)
        if env is None:
            none_streak += 1
            if none_streak >= 5:
                return {"status": "failed", "summary": {}}
        else:
            none_streak = 0
            st = env.get("status")
            if st in _TERMINAL:
                return {"status": st, "summary": env.get("summary") or {}}
        if time.monotonic() >= deadline:
            return {"status": "failed", "summary": {}}
        time.sleep(_POLL_INTERVAL_SEC)


def _aggregate_returncode(summary: dict) -> int:
    rcs = (summary or {}).get("returncodes") or {}
    try:
        return max((abs(int(v)) for v in rcs.values()), default=0)
    except (TypeError, ValueError):
        return 0


def _slugs_for_solutions(solutions, workspace_root, store) -> list:
    catalogo = store.load_catalog(str(workspace_root)).get("solutions", [])
    por_ruta = {os.path.normpath(str(s.get("sln_path") or "")): s.get("slug")
                for s in catalogo if s.get("slug")}
    out: list = []
    for sln in solutions:
        slug = por_ruta.get(os.path.normpath(str(sln)))
        if slug and slug not in out:
            out.append(slug)
    return out


def verify_build(*, ado_id: int, project_name: str, workspace_root,
                 execution_id: int = 0) -> BuildVerdict:
    """Corre el build real y persiste el veredicto. Nunca devuelve "ok" sin prueba."""
    try:
        from services.client_profile import load_effective_client_profile

        profile = load_effective_client_profile(project_name) or {}
    except Exception:  # noqa: BLE001
        profile = {}

    entry = resolve_build_entry(profile, workspace_root)
    now = _utcnow_iso()

    if entry["entry_kind"] != "sln":
        # Sin .sln no hay entrada verificable ⇒ BLOQUEANTE. Nunca "Build OK".
        v = _not_verified(entry["reason"], entry_kind=entry["entry_kind"],
                          solutions=tuple(entry["solutions"]), verified_at=now,
                          execution_id=execution_id)
        write_verdict(ado_id, workspace_root, v)
        return v

    toolchain = _detect_toolchain_safe()
    if not toolchain.get("available"):
        v = _not_verified("toolchain_missing", entry_kind="sln",
                          solutions=tuple(entry["solutions"]), toolchain=toolchain,
                          verified_at=now, execution_id=execution_id)
        write_verdict(ado_id, workspace_root, v)
        return v

    try:
        from services import solution_builder, solution_store
    except ImportError:
        v = _not_verified("build_workshop_unavailable", entry_kind="sln",
                          solutions=tuple(entry["solutions"]), toolchain=toolchain,
                          verified_at=now, execution_id=execution_id)
        write_verdict(ado_id, workspace_root, v)
        return v

    solution_store.rescan_and_save(str(workspace_root))
    slugs = _slugs_for_solutions(entry["solutions"], workspace_root, solution_store)
    if not slugs:
        v = _not_verified("build_failed", entry_kind="sln",
                          solutions=tuple(entry["solutions"]), toolchain=toolchain,
                          verified_at=now, execution_id=execution_id)
        write_verdict(ado_id, workspace_root, v)
        return v

    build_id = solution_builder.start_build(slugs, len(slugs) > 1, str(workspace_root))
    envelope = _poll_until_terminal(solution_builder, build_id)
    status = envelope.get("status")
    summary = envelope.get("summary") or {}
    rc = _aggregate_returncode(summary)
    ok = (status == "success" and rc == 0)
    base_dir = summary.get("base_dir") or ""
    resumen = os.path.join(base_dir, "build.summary.json") if base_dir else ""

    v = BuildVerdict(
        ok=ok, gate_ok=ok, entry_kind="sln",
        solution=(entry["solutions"][0] if entry["solutions"] else ""),
        solutions=tuple(entry["solutions"]),
        returncode=rc,
        summary_path=resumen,
        reason=("ok" if ok else "build_failed"),
        toolchain={"available": True, "builder": toolchain.get("builder"),
                   "version": toolchain.get("version")},
        build_id=build_id, verified_at=now, execution_id=execution_id,
        blocking_findings=(), warnings=(),
    )
    write_verdict(ado_id, workspace_root, v)
    return v


# ── F3 — helpers públicos de resolución (los reusan F4/F5 y el Plan 211) ─────

def project_name_for_ado(ado_id: int):
    try:
        from db import session_scope
        from models import Ticket

        with session_scope() as s:
            t = s.query(Ticket).filter(Ticket.ado_id == ado_id).first()
            return t.stacky_project_name if t else None
    except Exception:  # noqa: BLE001
        logger.debug("project_name_for_ado falló (no crítico)", exc_info=True)
        return None


def workspace_root_for_ado(ado_id: int):
    """Workspace del proyecto del ticket, o None (los callers degradan)."""
    try:
        name = project_name_for_ado(ado_id)
        if not name:
            return None
        try:
            from project_manager import get_project_config

            cfg = get_project_config(name) or {}
            ws = (cfg.get("workspace_root") or "").strip()
            if ws:
                return ws
        except Exception:  # noqa: BLE001
            logger.debug("get_project_config falló", exc_info=True)
        from runtime_paths import _active_workspace_root

        activo = _active_workspace_root()
        return str(activo) if activo else None
    except Exception:  # noqa: BLE001
        logger.debug("workspace_root_for_ado falló (no crítico)", exc_info=True)
        return None


def latest_execution_id_for_ado(ado_id: int) -> int:
    """Ejecución más reciente del ticket. 0 si no hay (el gate degrada)."""
    try:
        from db import session_scope
        from models import AgentExecution, Ticket

        with session_scope() as s:
            row = (
                s.query(AgentExecution)
                .join(Ticket, Ticket.id == AgentExecution.ticket_id)
                .filter(Ticket.ado_id == ado_id)
                .order_by(AgentExecution.id.desc())
                .first()
            )
            return int(row.id) if row else 0
    except Exception:  # noqa: BLE001
        logger.debug("latest_execution_id_for_ado falló (no crítico)", exc_info=True)
        return 0


# ── F4 — gate del estado final ───────────────────────────────────────────────

def _flag_on() -> bool:
    try:
        from config import config as _cfg

        return bool(getattr(_cfg, "STACKY_DEV_BUILD_VERIFY_ENABLED", False))
    except Exception:  # noqa: BLE001
        return False


def _review_state_for(project_name):
    """Primer `input_states` del rol developer. Se lee el perfil DIRECTO: importar
    de `api.tickets` invertiría la dependencia (service→api) y rompería el arranque."""
    try:
        from services.client_profile import load_effective_client_profile

        machine = ((load_effective_client_profile(project_name) or {})
                   .get("tracker_state_machine", {}) or {}).get("developer", {}) or {}
        estados = machine.get("input_states") or []
        return estados[0] if estados else None
    except Exception:  # noqa: BLE001
        logger.debug("no se pudo resolver el estado de revisión", exc_info=True)
        return None


def gate_final_state(*, project_name, agent_type, ado_id: int, workspace_root,
                     proposed_state, execution_id: int = 0) -> tuple:
    """`(estado_efectivo, meta)`. El developer no avanza sin veredicto de máquina FRESCO.

    Nunca lanza. Degrada al estado de revisión del rol; si no hay, cancela la
    transición (mejor dejar el ticket donde está que avanzarlo en falso).
    """
    try:
        if not _flag_on() or agent_type != "developer":
            return proposed_state, {"applied": False, "reason": "not_applicable"}

        verdict = read_verdict(ado_id, workspace_root)
        if verdict is None:
            reason = "not_verified"
            fresco_ok = False
        elif execution_id and verdict.execution_id and execution_id != verdict.execution_id:
            # Veredicto de OTRA corrida: no vale como verde de la actual.
            reason = "stale_verdict"
            fresco_ok = False
        else:
            reason = verdict.reason
            fresco_ok = bool(verdict.gate_ok)

        if fresco_ok:
            return proposed_state, {"applied": True, "gate_ok": True, "reason": reason}

        review_state = _review_state_for(project_name)
        return review_state, {"applied": True, "gate_ok": False, "reason": reason,
                              "downgraded_from": proposed_state}
    except Exception:  # noqa: BLE001
        logger.debug("gate_final_state falló (no crítico)", exc_info=True)
        return proposed_state, {"applied": False, "reason": "exception"}


# ── F5 — anotación autoritativa del deliverable ──────────────────────────────

_EVIDENCE_CONTRIBUTORS: list = []

_MARKER = "<!-- dev_build_verify -->"
_STRUCK_BUILD_CLAIM = ('<span style="color:#888"><s>Build OK (afirmación no verificada '
                       "— ver veredicto de máquina)</s></span>")
_STRUCK_TEXT = "<s>Build OK (no verificado)</s>"

_REASON_LABEL = {
    "ok": "La solución compiló sin errores.",
    "no_sln": "No se encontró ninguna solución .sln para compilar.",
    "csproj_not_allowed": ("Solo hay proyectos sueltos (.csproj) y el perfil no los "
                           "acepta como entrada de build."),
    "csproj_entry": "La entrada de build es un .csproj suelto, no una solución.",
    "build_failed": "La compilación devolvió errores.",
    "toolchain_missing": "Falta el toolchain .NET en esta máquina (ver doctor).",
    "build_workshop_unavailable": "El Taller de Compilación no está disponible.",
    "workspace_missing": "No se pudo resolver el workspace del proyecto.",
    "stale_verdict": "El veredicto disponible es de otra corrida.",
    "not_verified": "Ninguna máquina verificó este build.",
}


def register_evidence_contributor(fn) -> None:
    """Seam para que otros planes sumen hallazgos al veredicto."""
    if fn not in _EVIDENCE_CONTRIBUTORS:
        _EVIDENCE_CONTRIBUTORS.append(fn)


def _authoritative_block(verdict: BuildVerdict) -> str:
    etiqueta = _REASON_LABEL.get(verdict.reason, verdict.reason)
    if verdict.gate_ok:
        cuerpo = (
            '<p><span style="color:green"><strong>✓ Build OK (verificado por máquina)'
            "</strong></span></p>"
            f"<p>Solución: {verdict.solution or '—'} · Toolchain: "
            f"{verdict.toolchain.get('builder') or '—'} · returncode: {verdict.returncode}</p>"
        )
        if verdict.summary_path:
            cuerpo += f"<p>Evidencia: {verdict.summary_path}</p>"
    else:
        cuerpo = (
            '<p><span style="color:red"><strong>✗ Build NO verificado</strong></span> — '
            f"{etiqueta}</p>"
        )
        if verdict.blocking_findings:
            filas = "".join(
                f"<li>{(f or {}).get('kind', '?')}: {(f or {}).get('detail', '')}</li>"
                for f in verdict.blocking_findings
            )
            cuerpo += f"<ul>{filas}</ul>"
    return f"{_MARKER}<h2>3. BUILD</h2>{cuerpo}"


_GREEN_CLAIM_RE = None
_PLAIN_CLAIM_RE = None
_SECTION_RE = None


def _regexes():
    global _GREEN_CLAIM_RE, _PLAIN_CLAIM_RE, _SECTION_RE
    if _GREEN_CLAIM_RE is None:
        import re

        _GREEN_CLAIM_RE = re.compile(
            r"<span[^>]*color\s*:\s*green[^>]*>\s*<strong>\s*[✓✔]?\s*Build OK.*?</strong>\s*</span>",
            re.IGNORECASE | re.DOTALL,
        )
        _PLAIN_CLAIM_RE = re.compile(r"(?<![\w>])[✓✔]\s*Build OK\b", re.IGNORECASE)
        _SECTION_RE = re.compile(r"<h2[^>]*>\s*3\.\s*BUILD\s*</h2>.*?(?=<hr|<h2|$)",
                                 re.IGNORECASE | re.DOTALL)
    return _GREEN_CLAIM_RE, _PLAIN_CLAIM_RE, _SECTION_RE


def annotate_build_evidence(*, ado_id: int, agent_type, workspace_root, html: str) -> str:
    """Reemplaza el "Build OK" narrado por el veredicto de máquina. Nunca lanza."""
    try:
        if not _flag_on() or agent_type != "developer" or not html:
            return html
        if _MARKER in html:
            return html  # idempotente

        verdict = read_verdict(ado_id, workspace_root) or _not_verified("not_verified")

        secciones: list = []
        nuevos_blocking: list = []
        nuevos_warn: list = []
        for contribuidor in list(_EVIDENCE_CONTRIBUTORS):
            try:
                aporte = contribuidor(ado_id, verdict) or {}
                if aporte.get("section_html"):
                    secciones.append(str(aporte["section_html"]))
                nuevos_blocking.extend(aporte.get("blocking") or [])
                nuevos_warn.extend(aporte.get("warnings") or [])
            except Exception:  # noqa: BLE001
                logger.debug("un contribuidor de evidencia falló (no crítico)", exc_info=True)

        if nuevos_blocking or nuevos_warn:
            blocking = tuple(verdict.blocking_findings) + tuple(nuevos_blocking)
            verdict = replace(
                verdict,
                blocking_findings=blocking,
                warnings=tuple(verdict.warnings) + tuple(nuevos_warn),
                gate_ok=(verdict.ok and verdict.entry_kind == "sln" and not blocking),
            )
            write_verdict(ado_id, workspace_root, verdict)

        green_re, plain_re, section_re = _regexes()
        neutralizados = 0
        if not verdict.gate_ok:
            html, n1 = green_re.subn(_STRUCK_BUILD_CLAIM, html)
            html, n2 = plain_re.subn(_STRUCK_TEXT, html)
            neutralizados = n1 + n2
            if neutralizados:
                logger.warning(
                    "dev_build_gate.claim_vs_machine_mismatch: ADO-%s narró build verde "
                    "sin respaldo (%d claim(s) neutralizados, reason=%s)",
                    ado_id, neutralizados, verdict.reason,
                )

        bloque = _authoritative_block(verdict) + "".join(secciones)
        if section_re.search(html):
            return section_re.sub(lambda _m: bloque, html, count=1)
        return html + bloque
    except Exception:  # noqa: BLE001
        logger.exception("annotate_build_evidence falló; se devuelve el HTML original")
        return html


def persist_verdict_summary(execution_id, ado_id: int, workspace_root) -> dict | None:
    """Plan 210 F7 — resumen del veredicto en `execution.metadata["build_verdict"]`
    para que la UI lo muestre. Best-effort: nunca lanza, nunca bloquea el publish.

    `blocking_findings`/`warnings` salen del veredicto YA fusionado con los aportes
    de los contribuidores; este módulo es el único dueño de esta escritura.
    """
    if not execution_id:
        return None
    try:
        verdict = read_verdict(ado_id, workspace_root)
        if verdict is None:
            return None
        resumen = {
            "gate_ok": bool(verdict.gate_ok),
            "reason": verdict.reason,
            "entry_kind": verdict.entry_kind,
            "solution": verdict.solution,
            "blocking_findings": list(verdict.blocking_findings),
            "warnings": list(verdict.warnings),
        }
        import json as _json

        from db import session_scope
        from models import AgentExecution

        with session_scope() as s:
            row = s.get(AgentExecution, execution_id)
            if row is None:
                return None
            meta: dict = {}
            if row.metadata_json:
                try:
                    cargado = _json.loads(row.metadata_json)
                    meta = cargado if isinstance(cargado, dict) else {}
                except (ValueError, TypeError):
                    meta = {}
            meta["build_verdict"] = resumen
            row.metadata_json = _json.dumps(meta, ensure_ascii=False, default=str)
        return resumen
    except Exception:  # noqa: BLE001
        logger.debug("no se pudo persistir el resumen del veredicto", exc_info=True)
        return None


__all__ = [
    "BuildVerdict", "_REASONS", "resolve_build_entry", "verdict_path",
    "write_verdict", "read_verdict", "verify_build", "replace",
    "project_name_for_ado", "workspace_root_for_ado", "latest_execution_id_for_ado",
    "gate_final_state", "register_evidence_contributor", "annotate_build_evidence",
    "persist_verdict_summary",
]
