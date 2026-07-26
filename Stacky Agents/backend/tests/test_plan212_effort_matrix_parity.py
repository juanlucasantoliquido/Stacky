"""Plan 212 F3 — La matriz modelo×effort tiene UNA sola verdad, verificada.

Hay cuatro copias de "qué effort soporta cada modelo": el JSON del catálogo, el
fallback de emergencia del backend, el del frontend y la función que degrada.
Si driftean, la UI ofrece algo que el CLI rechaza. Estos tests las atan.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.llm_router import clamp_effort_for_model  # noqa: E402
from services.model_catalog import _EMERGENCY_FALLBACK  # noqa: E402

_EFFORTS = ("low", "medium", "high", "xhigh", "max")
_FRONT_FALLBACK = (
    ROOT.parent / "frontend" / "src" / "services" / "modelCatalogFallback.ts"
)


def _archivo() -> dict:
    path = ROOT / "config" / "model_catalog.json"
    return json.loads(path.read_text(encoding="utf-8"))["runtimes"]["claude_code_cli"]


def test_catalog_matches_clamp_for_every_pair():
    soporte = _archivo()["effort_support"]

    for modelo, soportados in soporte.items():
        for effort in _EFFORTS:
            intacto = clamp_effort_for_model(effort, modelo) == effort
            assert intacto is (effort in soportados), (
                f"{modelo} + {effort}: catálogo dice soportado={effort in soportados} "
                f"pero clamp_effort_for_model dice {intacto}"
            )


def test_effort_degrade_matches_clamp():
    """Lo que la UI promete que va a pasar es lo que realmente pasa."""
    cli = _archivo()
    degrade = cli["effort_degrade"]

    assert set(degrade) == set(cli["effort_support"]), \
        "effort_degrade tiene que cubrir los mismos modelos que effort_support"

    for modelo, soportados in cli["effort_support"].items():
        no_soportados = [e for e in _EFFORTS if e not in soportados]
        assert set(degrade[modelo]) == set(no_soportados), (
            f"{modelo}: effort_degrade debe listar exactamente los no soportados "
            f"({no_soportados}), no {sorted(degrade[modelo])}"
        )
        for effort in no_soportados:
            assert degrade[modelo][effort] == clamp_effort_for_model(effort, modelo)


def test_runner_accepts_all_catalog_efforts():
    from services.claude_code_cli_runner import CLI_VALID_EFFORTS

    cli = _archivo()
    ofrecidos = {e["id"] for e in cli["efforts"]} | {
        e for lista in cli["effort_support"].values() for e in lista
    }

    assert ofrecidos <= set(CLI_VALID_EFFORTS), (
        f"el catálogo ofrece efforts que el runner descarta en silencio: "
        f"{sorted(ofrecidos - set(CLI_VALID_EFFORTS))}"
    )


def test_emergency_fallback_is_not_poorer_than_file():
    """Si el archivo no se puede leer, el operador no puede ver MENOS opciones."""
    archivo = _archivo()
    emergencia = _EMERGENCY_FALLBACK["runtimes"]["claude_code_cli"]

    ids_archivo = {m["id"] for m in archivo["models"]}
    ids_emergencia = {m["id"] for m in emergencia["models"]}
    assert ids_archivo <= ids_emergencia, \
        f"el fallback esconde modelos: {sorted(ids_archivo - ids_emergencia)}"

    ef_archivo = {e["id"] for e in archivo["efforts"]}
    ef_emergencia = {e["id"] for e in emergencia["efforts"]}
    assert ef_archivo <= ef_emergencia, \
        f"el fallback esconde efforts: {sorted(ef_archivo - ef_emergencia)}"

    assert emergencia["effort_support"] == archivo["effort_support"]
    assert emergencia["effort_degrade"] == archivo["effort_degrade"]


def test_frontend_fallback_mirrors_backend():
    """Los dos lados de la red tienen que ofrecer lo mismo (C5 del 159)."""
    src = _FRONT_FALLBACK.read_text(encoding="utf-8")
    emergencia = _EMERGENCY_FALLBACK["runtimes"]["claude_code_cli"]

    ids = re.findall(r'id:\s*"([^"]+)"', src)
    modelos_front = {i for i in ids if i.startswith("claude-")}
    efforts_front = {i for i in ids if i in _EFFORTS}

    assert modelos_front == {m["id"] for m in emergencia["models"]}
    assert efforts_front == {e["id"] for e in emergencia["efforts"]}
