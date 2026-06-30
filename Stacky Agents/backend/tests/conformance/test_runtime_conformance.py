"""V2.1 (plan 22) — Runtime Conformance Suite.

Garantiza, por introspección estática (sin spawnear binarios reales), que cada
runtime CLI declarado en `CAPABILITIES` está cableado a los seams compartidos del
arnés. Es el contrato que cualquier runtime nuevo (Gemini CLI, proveedor X) debe
cumplir: implementar el contrato + pasar esta suite (ver checklist de onboarding).

Por qué introspección y no ejecución: los checks deben fallar si alguien REMUEVE
el cableado de un runner (p.ej. saca el RunawayGuard) — "test del test" abajo —
sin depender de binarios CLI instalados ni de fixtures frágiles.

Cubre los 7 puntos del plan §V2.1: (1) post-run finalize, (2) telemetría
persistida, (3) claves canónicas de metadata no renombradas, (4) resume si
supports_resume, (5) RunawayGuard, (6) inyecciones/taxonomía de fallos vía seams,
(7) artefacto reproducible (repro script). Añade V1.1 (prompt_sha) y V2.4
(run_fingerprint) como claves canónicas nuevas.
"""
from __future__ import annotations

from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]


def _capabilities():
    import sys

    sys.path.insert(0, str(BACKEND))
    from harness.capabilities import CAPABILITIES

    return CAPABILITIES


# Runtimes con runner CLI propio (los que esta suite inspecciona a fondo).
RUNNER_SOURCES = {
    "claude_code_cli": BACKEND / "services" / "claude_code_cli_runner.py",
    "codex_cli": BACKEND / "services" / "codex_cli_runner.py",
}
CLI_RUNTIMES = sorted(RUNNER_SOURCES)  # solo los que tienen runner CLI propio
# Plan 49 F3 — TODOS los runtimes declarados (incluye github_copilot).
ALL_RUNTIMES = sorted(_capabilities())


def _source(runtime: str) -> str:
    return RUNNER_SOURCES[runtime].read_text(encoding="utf-8")


def _has_any(source: str, alternatives: list[str]) -> bool:
    return any(token in source for token in alternatives)


# ── Conformance por runtime CLI (parametrizado) ──────────────────────────────


# Plan 49 F3 — el check de CAPACIDADES corre para los 3 runtimes (incl. github_copilot),
# no solo los que tienen runner CLI propio.
@pytest.mark.parametrize("runtime", ALL_RUNTIMES)
def test_runtime_declared_in_capabilities(runtime):
    caps = _capabilities()
    assert runtime in caps
    rc = caps[runtime]
    for attr in (
        "writes_artifacts",
        "supports_stdin_feedback",
        "supports_resume",
        "supports_mcp",
        "has_stream_telemetry",
    ):
        assert isinstance(getattr(rc, attr), bool)


def test_github_copilot_exception_documented():
    """github_copilot no tiene runner CLI dedicado (flujo estándar en
    agent_runner.py). Su exclusión de los tests de cableado CLI es deliberada,
    no un olvido. Este test fija esa decisión: si alguien agrega un runner CLI
    de copilot, debe sumarlo a RUNNER_SOURCES y este assert lo recordará."""
    caps = _capabilities()
    assert "github_copilot" in caps
    assert "github_copilot" not in RUNNER_SOURCES, (
        "Si github_copilot gana runner CLI propio, agregalo a RUNNER_SOURCES "
        "y conectalo a los seams del arnés (post_run, telemetry, RunawayGuard)."
    )
    cap = caps["github_copilot"]
    assert cap.writes_artifacts is True
    assert cap.supports_resume is False
    assert cap.supports_mcp is False


@pytest.mark.parametrize("runtime", CLI_RUNTIMES)
def test_post_run_finalize_wired(runtime):
    assert _has_any(_source(runtime), ["post_run", "finalize_run"]), (
        f"{runtime}: falta integración con harness.post_run"
    )


@pytest.mark.parametrize("runtime", CLI_RUNTIMES)
def test_telemetry_persisted(runtime):
    assert _has_any(_source(runtime), ["telemetry"]), f"{runtime}: sin telemetría"


@pytest.mark.parametrize("runtime", CLI_RUNTIMES)
def test_runaway_guard_wired(runtime):
    assert _has_any(_source(runtime), ["RunawayGuard", "runaway_guard"]), (
        f"{runtime}: RunawayGuard no cableado"
    )


@pytest.mark.parametrize("runtime", CLI_RUNTIMES)
def test_failure_taxonomy_wired(runtime):
    assert _has_any(_source(runtime), ["failure", "classify"]), (
        f"{runtime}: taxonomía de fallos (V0.4) no cableada"
    )


@pytest.mark.parametrize("runtime", CLI_RUNTIMES)
def test_repro_script_wired(runtime):
    assert _has_any(_source(runtime), ["write_repro_script", "repro"]), (
        f"{runtime}: no genera artefacto reproducible"
    )


@pytest.mark.parametrize("runtime", CLI_RUNTIMES)
def test_canonical_metadata_keys_present(runtime):
    src = _source(runtime)
    # Claves canónicas NO renombrables + nuevas (V1.1 prompt_sha, V2.4 fingerprint).
    assert "prompt_sha" in src, f"{runtime}: no sella prompt_sha (V1.1)"
    assert "run_fingerprint" in src, f"{runtime}: no sella run_fingerprint (V2.4)"


@pytest.mark.parametrize("runtime", CLI_RUNTIMES)
def test_resume_integrable_when_supported(runtime):
    rc = _capabilities()[runtime]
    if not rc.supports_resume:
        pytest.skip(f"{runtime} no soporta resume")
    src = _source(runtime)
    assert "resume" in src, f"{runtime}: supports_resume=True pero no integra resume"


# ── Consistencia global de capabilities + resume ─────────────────────────────


def test_resume_session_keys_consistent():
    """Todo runtime con supports_resume debe tener session key y flags de resume."""
    from harness.resume import _RESUME_FLAG, _SESSION_KEY

    caps = _capabilities()
    for runtime, rc in caps.items():
        if rc.supports_resume:
            assert runtime in _SESSION_KEY, f"{runtime}: falta _SESSION_KEY"
            assert runtime in _RESUME_FLAG, f"{runtime}: falta _RESUME_FLAG"


def test_session_key_string_sealed_by_runner():
    """La clave de sesión canónica del runtime aparece en su runner (no renombrada)."""
    from harness.resume import _SESSION_KEY

    for runtime in CLI_RUNTIMES:
        key = _SESSION_KEY.get(runtime)
        if not key:
            continue
        assert key in _source(runtime), (
            f"{runtime}: la clave canónica de sesión '{key}' no aparece en el runner"
        )


# ── Test del test: la suite debe FALLAR si se remueve un cableado ────────────


def test_conformance_detects_missing_wiring():
    """Si un runner perdiera el RunawayGuard, el check correspondiente fallaría."""
    fake_runner_without_runaway = "def run(): telemetry.persist(); post_run.finalize_run()"
    assert not _has_any(fake_runner_without_runaway, ["RunawayGuard", "runaway_guard"])
    # …y un runner completo lo tiene:
    assert _has_any("g = RunawayGuard()", ["RunawayGuard", "runaway_guard"])


# ── Plan 51 F5 — Conformance + centinela de no-determinismo del epic_gate ─────
#
# Las 3 runtimes importan harness.epic_gate idéntico (funciones puras). El WIRING
# del autopublish es Claude-CLI-only, pero las funciones puras deben ser
# deterministas e independientes del runtime, locale y orden de entrada.

_GATE_HTML_CASES = [
    "<h1>E</h1><h2>RF-1</h2><p>x</p>",                       # verde
    "<h1>E</h1><h2>RF-3</h2><p>x</p>",                       # hueco (needs_review)
    "solo narración sin épica",                              # not_epic
    "<h1>E</h1><h2>RF-1</h2><p>proceso Fantasma</p>",        # catálogo
]
_GATE_CATALOG = [{"name": "RSCore"}]


def _looks(html):
    from api.tickets import _looks_like_epic
    return _looks_like_epic(html)


def _struct(html):
    from api.tickets import _epic_grounding_warnings
    return _epic_grounding_warnings(html)


def test_epic_gate_is_deterministic_and_idempotent():
    from harness.epic_gate import evaluate_epic_gate
    for html in _GATE_HTML_CASES:
        kwargs = dict(
            clean_html=html, structural_warnings=_struct(html),
            process_catalog=_GATE_CATALOG, catalog_blocking_enabled=True,
            looks_like_epic_fn=_looks,
        )
        v1 = evaluate_epic_gate(**kwargs)
        v2 = evaluate_epic_gate(**kwargs)
        assert v1 == v2


def test_epic_gate_independent_of_locale():
    import os
    from harness.epic_gate import evaluate_epic_gate
    html = "<h1>E</h1><h2>RF-3</h2><p>proceso Fantasma</p>"
    kwargs = dict(
        clean_html=html, structural_warnings=_struct(html),
        process_catalog=_GATE_CATALOG, catalog_blocking_enabled=True,
        looks_like_epic_fn=_looks,
    )
    base = evaluate_epic_gate(**kwargs)
    saved = {k: os.environ.get(k) for k in ("LANG", "LC_ALL")}
    try:
        os.environ["LANG"] = "C"
        os.environ["LC_ALL"] = "C"
        assert evaluate_epic_gate(**kwargs) == base
    finally:
        for k, val in saved.items():
            if val is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = val


def test_classify_severity_result_is_sorted():
    # Centinela: si alguien quitara el `sorted` del clasificador, las claves
    # podrían venir en orden no determinista. Aquí afirmamos orden estable.
    from harness.epic_gate import classify_structural_severity
    w = [
        "epic_structure: secuencia RF no consecutiva, faltan: [2]",
        "epic_structure: números RF duplicados: [3]",
        "epic_structure: hay headings vacíos",
    ]
    res = classify_structural_severity(w)
    assert list(res.keys()) == sorted(res.keys())


def test_epic_gate_importable_independent_of_runtime():
    # La función pura no depende del runtime; el import debe funcionar siempre.
    import importlib
    mod = importlib.import_module("harness.epic_gate")
    assert hasattr(mod, "evaluate_epic_gate")
    assert hasattr(mod, "GateVerdict")


# ── Plan 53 F4 — Conformance del selector adaptativo (paridad G2 + C9) ────────


def test_adaptive_selector_is_runtime_agnostic():
    """G2 — select() produce propuesta sin parámetro de runtime (pura, idéntica para los 3).

    La función pura NO debe recibir runtime. Este test fija el contrato: si alguien
    agregara un parámetro runtime a select(), esta suite lo detecta.
    """
    import inspect
    from services import adaptive_selector
    params = inspect.signature(adaptive_selector.select).parameters
    assert "runtime" not in params, (
        "select() NO debe depender del runtime (paridad G2 — ver §3 del plan 53)"
    )
    # Verificar que produce una Selection para cada confidence representativo.
    from services.adaptive_selector import select
    for conf in (0.1, 0.55, 0.95, None):
        out = select(conf, base_model=None, base_effort="high")
        assert hasattr(out, "model") and hasattr(out, "effort") and hasattr(out, "reason"), (
            f"select({conf}) debe devolver Selection con model/effort/reason; got {out}"
        )


def test_adaptive_selector_adapts_to_confidence_levels():
    """C9 RESUELTO — select() PROPONE DISTINTO según confidence (es adaptativa de verdad).

    Low confidence debe ser más caro (Opus/max); high confidence más barato (Sonnet/low).
    Si ambos devuelven lo mismo, el selector no está adaptando nada.
    """
    from services.adaptive_selector import select
    low_conf = select(0.1, base_model=None, base_effort="high")
    high_conf = select(0.95, base_model=None, base_effort="high")

    # NO pueden ser idénticas.
    assert low_conf != high_conf, (
        f"select() debe adaptar: confidence=0.1 → {low_conf}; "
        f"confidence=0.95 → {high_conf}. Deben diferir."
    )

    # Validar dirección de adaptación: bajo confidence → más caro/pesado.
    model_cost_map = {"claude-sonnet-4-6": 1, "claude-opus-4-8": 2}
    if low_conf.model and high_conf.model:
        low_cost = model_cost_map.get(low_conf.model, 0)
        high_cost = model_cost_map.get(high_conf.model, 0)
        assert low_cost >= high_cost, (
            f"Low confidence debe proponer modelo >= costoso que high confidence. "
            f"low={low_conf.model}(cost={low_cost}), high={high_conf.model}(cost={high_cost})"
        )

    # Validar dirección de effort: bajo confidence → effort >= al de alto confidence.
    effort_rank = {"low": 0, "medium": 1, "high": 2, "xhigh": 3, "max": 4}
    low_rank = effort_rank.get(low_conf.effort, -1)
    high_rank = effort_rank.get(high_conf.effort, -1)
    assert low_rank >= high_rank, (
        f"Low confidence debe tener effort >= al de high confidence. "
        f"low={low_conf.effort}(rank={low_rank}), high={high_conf.effort}(rank={high_rank})"
    )
