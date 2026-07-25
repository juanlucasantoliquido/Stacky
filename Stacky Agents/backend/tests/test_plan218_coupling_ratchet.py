"""tests/test_plan218_coupling_ratchet.py -- Plan 218 F1.

Censo ejecutable del acoplamiento a Azure DevOps + RATCHET: la métrica solo puede
BAJAR. Es el mecanismo que hace converger los 18 subplanes 219..236 (sin esto,
un subplan reduce acoplamiento mientras otro lo aumenta).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.provider_coupling_audit import (  # noqa: E402
    ADAPTER_ALLOWLIST,
    NEUTRAL_REGISTRY_ALLOWLIST,
    render_report_markdown,
    scan_backend_coupling,
)

_BASELINE_PATH = _BACKEND / "tests" / "provider_coupling_baseline.json"


def _baseline() -> dict:
    return json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))


def test_scan_es_determinista():
    assert scan_backend_coupling() == scan_backend_coupling()


def test_scan_excluye_tests_y_venv():
    scan = scan_backend_coupling()
    for clave in ("ado_importer_files", "tracker_literal_files"):
        for ruta in scan[clave]:
            assert not ruta.startswith("tests/"), ruta
            assert ".venv/" not in ruta and not ruta.startswith("venv/"), ruta


def test_scan_excluye_familia_ado():
    """La familia services/ado_*.py NO cuenta como IMPORTADOR de sí misma.

    (El censo de LITERALES sí la incluye a propósito: la meta de K4 —"≤ 20
    (adaptadores + factories + defaults)"— cuenta explícitamente a los adaptadores.)
    """
    scan = scan_backend_coupling()
    for ruta in scan["ado_importer_files"]:
        assert not ruta.startswith("services/ado_"), ruta


def _assert_no_crece(scan: dict, clave: str, detalle_clave: str | None = None):
    base = _baseline()[clave]
    actual = scan[clave]
    detalle = ""
    if detalle_clave:
        detalle = "\nArchivos actuales:\n" + "\n".join(
            f"  {k}: {v}" for k, v in sorted(scan[detalle_clave].items())
        )
    assert actual <= base, (
        f"RATCHET ROTO: {clave} subió de {base} a {actual}. El acoplamiento a "
        f"Azure DevOps solo puede BAJAR (Plan 218 F1).{detalle}"
    )


def test_ratchet_importers_no_crece():
    _assert_no_crece(scan_backend_coupling(), "ado_importer_file_count", "ado_importer_files")


def test_ratchet_literales_no_crece():
    _assert_no_crece(scan_backend_coupling(), "tracker_literal_occurrences", "tracker_literal_files")


def test_ratchet_sitios_adoclient_no_crece():
    _assert_no_crece(scan_backend_coupling(), "ado_client_lines_in_tickets")


def test_ratchet_rutas_ado_no_crece():
    _assert_no_crece(scan_backend_coupling(), "ado_route_count")


def test_allowlist_de_adaptadores_es_exacta():
    """Cada ruta de ADAPTER_ALLOWLIST existe en disco (sin entradas fantasma)."""
    for ruta in ADAPTER_ALLOWLIST:
        assert (_BACKEND / ruta).exists(), f"entrada fantasma en ADAPTER_ALLOWLIST: {ruta}"


def test_allowlist_neutral_no_se_usa_para_esconder_acoplamiento():
    """C5: la exención vale para el LITERAL, nunca para el import.

    Un archivo "neutral" que importa el cliente de ADO deja este test ROJO.
    """
    scan = scan_backend_coupling()
    for ruta in NEUTRAL_REGISTRY_ALLOWLIST:
        path = _BACKEND / ruta
        if not path.exists():
            continue  # su fase todavía no lo creó — legítimo
        assert ruta not in scan["ado_importer_files"], (
            f"{ruta} está en NEUTRAL_REGISTRY_ALLOWLIST pero importa services.ado_*: "
            "la exención cubre el literal, no el import."
        )


def test_reporte_markdown_tiene_todas_las_secciones():
    md = render_report_markdown(scan_backend_coupling())
    for clave in (
        "ado_importer_file_count",
        "ado_importer_occurrences",
        "tracker_literal_file_count",
        "tracker_literal_occurrences",
        "ado_client_lines_in_tickets",
        "ado_route_count",
    ):
        assert clave in md, f"falta la métrica {clave} en el reporte"
