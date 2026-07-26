"""Plan 211 F3 — Los dos contribuidores de evidencia del veredicto de build.

Empaqueta el inspector post-build (Capa B) y el barrido de residuos (Capa C) como
contribuidores que el gate de build del Developer invoca al anotar el deliverable.
Un hallazgo bloqueante de cualquiera de los dos baja el `gate_ok` — el mecanismo
lo provee el gate, acá solo se aportan los findings.

Cada capa está gateada por su propia flag y aislada: si una falla o está apagada,
la otra sigue.
"""
from __future__ import annotations

import html as _html
import logging

from services import dev_build_verify, port_residue_scanner, post_build_inspector

logger = logging.getLogger(__name__)

_REGISTERED = False


def _empty() -> dict:
    return {"title": "", "section_html": "", "blocking": [], "warnings": []}


def _to_contribution(title: str, dicts: list) -> dict:
    blocking = [d for d in dicts if d.get("severity") == "blocking"]
    warnings = [d for d in dicts if d.get("severity") != "blocking"]
    if not dicts:
        return {"title": title, "section_html": "", "blocking": [], "warnings": []}

    color = "red" if blocking else "#b8860b"
    filas = "".join(
        "<tr><td>{sev}</td><td>{file}</td><td>{detail}</td></tr>".format(
            sev=_html.escape(str(d.get("severity", ""))),
            file=_html.escape(str(d.get("file", ""))),
            detail=_html.escape(str(d.get("detail", ""))),
        )
        for d in dicts
    )
    section_html = (
        f'<h3 style="color:{color}">{_html.escape(title)}</h3>'
        "<table><thead><tr><th>Severidad</th><th>Archivo</th><th>Detalle</th></tr>"
        f"</thead><tbody>{filas}</tbody></table>"
    )
    return {"title": title, "section_html": section_html,
            "blocking": blocking, "warnings": warnings}


def _ticket_ctx(ado_id: int) -> tuple:
    """Proyecto del TICKET + su workspace + catálogo de tokens ajenos.

    El catálogo excluye el proyecto del ticket (no el activo global, que en
    multicliente puede apuntar a otro cliente y producir una tormenta de
    bloqueantes sobre el proyecto correcto).
    """
    project_name = dev_build_verify.project_name_for_ado(ado_id)
    ws = dev_build_verify.workspace_root_for_ado(ado_id)
    catalog = port_residue_scanner.build_foreign_token_catalog(project_name)
    return project_name, str(ws or ""), catalog


def _project_files_for_solutions(solutions, ws: str) -> list:
    """Las .sln construidas + sus .csproj. Degrada a solo las .sln sin el scanner."""
    archivos = [str(s) for s in (solutions or [])]
    try:
        from services.solution_scanner import _parse_sln_projects

        for sln in list(archivos):
            for proyecto in _parse_sln_projects(sln):
                ruta = proyecto.get("csproj_path")
                if ruta and ruta not in archivos:
                    archivos.append(ruta)
    except Exception:  # noqa: BLE001
        logger.debug("scanner de soluciones no disponible; solo .sln", exc_info=True)
    return archivos


def _inspect_contributor(ado_id: int, verdict) -> dict:
    try:
        import config as _config

        if not getattr(_config.config, "STACKY_DEV_POST_BUILD_INSPECT_ENABLED", False):
            return _empty()
        if not getattr(verdict, "solutions", None):
            return _empty()  # sin build no hay project files que inspeccionar
        _pn, ws, foreign = _ticket_ctx(ado_id)
        archivos = _project_files_for_solutions(verdict.solutions, ws)
        findings = post_build_inspector.inspect_projects(
            archivos, workspace_root=ws, foreign_tokens=foreign)
        return _to_contribution("Inspección post-build",
                                post_build_inspector.findings_to_dicts(findings))
    except Exception:  # noqa: BLE001
        logger.debug("inspector post-build falló (no crítico)", exc_info=True)
        return _empty()


def _residue_contributor(ado_id: int, verdict) -> dict:
    try:
        import config as _config

        if not getattr(_config.config, "STACKY_DEV_PORT_RESIDUE_SCAN_ENABLED", False):
            return _empty()
        project_name, ws, catalog = _ticket_ctx(ado_id)
        allowlist = port_residue_scanner.allowlist_for_project(project_name)
        archivos = port_residue_scanner.changed_files(ws)
        findings = port_residue_scanner.scan_files_for_foreign_tokens(
            archivos, catalog, workspace_root=ws, allowlist=allowlist)
        return _to_contribution("Residuos de port entre clientes",
                                port_residue_scanner.residue_to_dicts(findings))
    except Exception:  # noqa: BLE001
        logger.debug("barrido de residuos falló (no crítico)", exc_info=True)
        return _empty()


def register(register_fn) -> None:
    """Registra ambos contribuidores UNA sola vez (create_app puede correr varias
    veces en tests; duplicarlos duplicaría los findings)."""
    global _REGISTERED
    if _REGISTERED:
        return
    register_fn(_inspect_contributor)
    register_fn(_residue_contributor)
    _REGISTERED = True
