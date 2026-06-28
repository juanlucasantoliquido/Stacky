"""
tests/test_no_adoclient_outside_ado_provider.py -- Guard anti-recableo (Plan 65 F10 ADICION #2).

Objetivo: detectar que NUEVO código no empiece a construir AdoClient() fuera de los
archivos autorizados, bypassando el puerto TrackerProvider.

Los archivos LEGACY (pre-Plan 65) que ya tenían AdoClient() están en _LEGACY_ALLOWLIST
y se excluyen. Si un archivo nuevo aparece en offenders, es señal de recableo.
"""
import re
import pathlib


# Archivos que PUEDEN construir AdoClient() — both legacy and new ports
_ALLOWED = {
    # Puerto formal y seam de construcción (Plan 65)
    "services/ado_provider.py",
    "services/ado_client.py",
    "services/project_context.py",
    # Archivos legacy pre-Plan 65 (tienen AdoClient() directo — no migrar sin plan)
    "api/pm.py",
    "services/ado_edit_learning.py",
    "services/ado_publisher.py",
    "services/ado_sync.py",
    "services/agent_completion_internal.py",
    "services/qa_browser_context.py",
    "services/ticket_service.py",
}


def test_no_adoclient_construction_outside_allowlist():
    """AdoClient() solo puede construirse en archivos de la allowlist (port + legacy).

    Si este test falla con un archivo NUEVO, ese archivo está recableando AdoClient()
    directamente en lugar de usar get_tracker_provider() o build_ado_client().
    """
    backend = pathlib.Path(__file__).resolve().parents[1]
    offenders = []

    for f in backend.rglob("*.py"):
        rel = f.relative_to(backend).as_posix()

        # Excluir tests y venv
        if rel.startswith("tests/") or ".venv" in rel or rel.startswith("evals/"):
            continue

        # Excluir la allowlist completa
        if any(a in rel for a in _ALLOWED):
            continue

        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        if re.search(r"AdoClient\(", text):
            offenders.append(rel)

    assert offenders == [], (
        f"AdoClient() construido FUERA de la allowlist en archivos nuevos: {offenders}\n"
        "Opciones:\n"
        "  1. Usar get_tracker_provider() del puerto TrackerProvider (Plan 65)\n"
        "  2. Usar build_ado_client() de services/project_context.py\n"
        "  3. Si es legacy legítimo, agregar a _ALLOWED en este test con comentario"
    )
