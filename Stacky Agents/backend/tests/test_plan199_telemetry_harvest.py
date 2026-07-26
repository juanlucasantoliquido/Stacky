"""Plan 199 F0 — Cosecha de telemetría desde los artefactos en disco.

Todo lo que los CLIs gastaron antes de que Stacky existiera —o fuera de Stacky—
está en disco y no figura en ningún tablero. Estos tests fijan que se descubre,
se normaliza igual que la telemetría en vivo, y que nada de esto puede romperse
por una carpeta ausente o un archivo a medio escribir.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services import telemetry_harvest as H  # noqa: E402

_DESDE = datetime(2000, 1, 1)


@pytest.fixture
def raices(tmp_path, monkeypatch):
    """Apunta las dos raíces a tmp_path: cero lectura del disco real del operador."""
    codex = tmp_path / "codex" / "sessions"
    claude = tmp_path / "claude" / "projects"
    codex.mkdir(parents=True)
    claude.mkdir(parents=True)
    monkeypatch.setattr(H, "_codex_sessions_root", lambda: codex)
    monkeypatch.setattr(H, "_claude_projects_root", lambda: claude)
    return {"codex": codex, "claude": claude}


def _jsonl(path: Path, eventos: list) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(e) for e in eventos), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Raíces ausentes: excepción dura #3
# ---------------------------------------------------------------------------

def test_sin_carpetas_no_rompe(monkeypatch):
    monkeypatch.setattr(H, "_codex_sessions_root", lambda: None)
    monkeypatch.setattr(H, "_claude_projects_root", lambda: None)

    assert H.discover_codex_rollouts(_DESDE) == []
    assert H.discover_claude_transcripts(_DESDE) == []
    assert H.harvest(_DESDE) == []


def test_copilot_devuelve_vacio_a_proposito():
    """No es un olvido de paridad: el bridge HTTP no deja sesión local."""
    assert H.discover_copilot_sessions(_DESDE) == []


def test_roots_override_malformado_se_ignora(monkeypatch):
    from config import config as cfg

    monkeypatch.setattr(cfg, "STACKY_TELEMETRY_HARVEST_ROOTS_JSON",
                        "{no soy json", raising=False)

    assert H._roots_override() == {}


def test_roots_override_valido_manda(tmp_path, monkeypatch):
    from config import config as cfg

    destino = tmp_path / "otro"
    destino.mkdir()
    monkeypatch.setattr(cfg, "STACKY_TELEMETRY_HARVEST_ROOTS_JSON",
                        json.dumps({"codex_cli": str(destino)}), raising=False)

    assert H._codex_sessions_root() == destino


# ---------------------------------------------------------------------------
# Descubrimiento
# ---------------------------------------------------------------------------

def test_descubre_rollouts_de_codex(raices):
    _jsonl(raices["codex"] / "2026" / "rollout-abc.jsonl", [{"x": 1}])
    _jsonl(raices["codex"] / "2026" / "otro.jsonl", [{"x": 1}])

    hallados = H.discover_codex_rollouts(_DESDE)

    assert [p.name for p in hallados] == ["rollout-abc.jsonl"], \
        "solo los rollout-*.jsonl son sesiones de codex"


def test_lookback_filtra_por_mtime(raices):
    viejo = _jsonl(raices["codex"] / "rollout-viejo.jsonl", [{"x": 1}])
    os.utime(viejo, (0, 0))
    _jsonl(raices["codex"] / "rollout-nuevo.jsonl", [{"x": 1}])

    desde = datetime.utcnow() - timedelta(days=1)

    assert [p.name for p in H.discover_codex_rollouts(desde)] == ["rollout-nuevo.jsonl"]


def test_limite_de_archivos_se_respeta(raices):
    for i in range(5):
        _jsonl(raices["codex"] / f"rollout-{i}.jsonl", [{"x": 1}])

    assert len(H.discover_codex_rollouts(_DESDE, limit=2)) == 2


# ---------------------------------------------------------------------------
# Parser de codex
# ---------------------------------------------------------------------------

def test_parse_codex_agrega_tokens(raices):
    path = _jsonl(raices["codex"] / "rollout-x.jsonl", [
        {"session_id": "s-1", "model": "gpt-5", "timestamp": "2026-07-20T10:00:00Z",
         "usage": {"input_tokens": 100, "output_tokens": 20}},
        {"usage": {"input_tokens": 50, "output_tokens": 10}},
    ])

    run = H.parse_codex_rollout(path)

    assert run.runtime == "codex_cli"
    assert run.session_id == "s-1"
    assert run.tokens_in == 150 and run.tokens_out == 30
    assert run.num_events == 2
    assert run.started_at == datetime(2026, 7, 20, 10, 0, 0), "naive-UTC"


def test_parse_codex_sin_uso_deja_tokens_en_none(raices):
    """Cero tokens y 'no sé cuántos tokens' no son lo mismo."""
    path = _jsonl(raices["codex"] / "rollout-y.jsonl", [{"foo": "bar"}])

    run = H.parse_codex_rollout(path)

    assert run.tokens_in is None and run.tokens_out is None


def test_parse_tolera_lineas_corruptas(raices):
    path = raices["codex"] / "rollout-z.jsonl"
    path.write_text(
        json.dumps({"usage": {"input_tokens": 10, "output_tokens": 5}})
        + "\n{ esto no es json\n"
        + json.dumps({"usage": {"input_tokens": 1, "output_tokens": 1}}),
        encoding="utf-8",
    )

    run = H.parse_codex_rollout(path)

    assert run.tokens_in == 11, "una línea a medias es normal, no un error"


def test_costo_reportado_gana_sobre_la_estimacion(raices):
    path = _jsonl(raices["codex"] / "rollout-c.jsonl", [
        {"model": "gpt-5", "usage": {"input_tokens": 1000, "output_tokens": 1000},
         "total_cost_usd": 0.42},
    ])

    run = H.parse_codex_rollout(path)

    assert run.total_cost_usd == 0.42
    assert run.cost_estimated is False


# ---------------------------------------------------------------------------
# Parser de claude
# ---------------------------------------------------------------------------

def test_parse_claude_lee_usage_por_mensaje(raices):
    path = _jsonl(raices["claude"] / "proj" / "uuid-1.jsonl", [
        {"type": "user", "sessionId": "abc", "timestamp": "2026-07-20T10:00:00Z",
         "cwd": "/home/juan/Stacky"},
        {"type": "assistant", "message": {"model": "claude-sonnet-5", "usage": {
            "input_tokens": 200, "output_tokens": 50, "cache_read_input_tokens": 10}}},
        {"type": "assistant", "message": {"usage": {
            "input_tokens": 100, "output_tokens": 25}}},
    ])

    run = H.parse_claude_transcript(path)

    assert run.runtime == "claude_code_cli"
    assert run.session_id == "abc"
    assert (run.tokens_in, run.tokens_out, run.cache_read_tokens) == (300, 75, 10)
    assert run.model == "claude-sonnet-5"


def test_parse_claude_estima_costo(raices):
    """El transcript no trae costo confiable: se estima y se dice que se estimó."""
    path = _jsonl(raices["claude"] / "uuid-2.jsonl", [
        {"type": "assistant", "message": {"model": "claude-sonnet-5", "usage": {
            "input_tokens": 10000, "output_tokens": 5000}}},
    ])

    run = H.parse_claude_transcript(path)

    if run.total_cost_usd is not None:
        assert run.cost_estimated is True, "un costo estimado tiene que declararse"


def test_parse_claude_sin_session_id_usa_el_stem(raices):
    path = _jsonl(raices["claude"] / "el-uuid.jsonl", [{"type": "system"}])

    assert H.parse_claude_transcript(path).session_id == "el-uuid"


def test_eventos_no_assistant_no_suman_uso(raices):
    path = _jsonl(raices["claude"] / "uuid-3.jsonl", [
        {"type": "user", "message": {"usage": {"input_tokens": 999}}},
    ])

    assert H.parse_claude_transcript(path).tokens_in is None


# ---------------------------------------------------------------------------
# Enmascarado
# ---------------------------------------------------------------------------

def test_nunca_sale_una_ruta_absoluta(raices):
    path = _jsonl(raices["claude"] / "uuid-4.jsonl", [
        {"type": "user", "cwd": "/home/juanluca/secreto/proyecto"},
    ])

    run = H.parse_claude_transcript(path)

    assert run.cwd == "proyecto"
    assert "/" not in (run.cwd or "") and "\\" not in (run.cwd or "")
    assert "/" not in run.artifact


def test_cwd_que_parece_secreto_se_redacta(monkeypatch):
    monkeypatch.setattr("services.secret_scanner.scan_secrets", lambda t: "token")

    assert H._mask_path("/x/loquesea") == "<redacted>"


# ---------------------------------------------------------------------------
# Contrato con el resto del sistema
# ---------------------------------------------------------------------------

def test_to_harness_telemetry_tiene_las_claves_del_extractor(raices):
    path = _jsonl(raices["codex"] / "rollout-k.jsonl", [
        {"session_id": "s", "usage": {"input_tokens": 1, "output_tokens": 2}}])

    payload = H.parse_codex_rollout(path).to_harness_telemetry()

    for clave in ("runtime", "session_id", "total_cost_usd", "input_tokens",
                  "output_tokens", "cache_read_tokens", "cost_estimated"):
        assert clave in payload, clave
    assert payload["source"] == "harvest_disk", \
        "un run cosechado no se puede confundir con uno capturado en vivo"


def test_harvest_deduplica_y_ordena(raices):
    _jsonl(raices["codex"] / "rollout-a.jsonl", [
        {"session_id": "dup", "timestamp": "2026-07-01T00:00:00Z"}])
    _jsonl(raices["codex"] / "rollout-b.jsonl", [
        {"session_id": "dup", "timestamp": "2026-07-02T00:00:00Z"}])
    _jsonl(raices["codex"] / "rollout-c.jsonl", [
        {"session_id": "otra", "timestamp": "2026-07-03T00:00:00Z"}])

    runs = H.harvest(_DESDE)

    assert len(runs) == 2, "la misma sesión en dos archivos es una sola corrida"
    assert runs[0].started_at > runs[1].started_at, "más nuevo primero"


def test_started_at_siempre_es_naive(raices):
    _jsonl(raices["codex"] / "rollout-tz.jsonl", [
        {"session_id": "s", "timestamp": "2026-07-01T00:00:00+03:00"}])

    run = H.harvest(_DESDE)[0]

    assert run.started_at.tzinfo is None, \
        "comparar naive contra aware es un TypeError esperando a pasar"
    assert run.started_at == datetime(2026, 6, 30, 21, 0, 0), "convertido a UTC"


def test_harvest_no_toca_la_base_de_datos():
    """F0 es puro: descubre y normaliza. La ingesta es otra fase."""
    fuente = (ROOT / "services" / "telemetry_harvest.py").read_text(encoding="utf-8")
    codigo = "\n".join(l for l in fuente.splitlines()
                       if not l.lstrip().startswith("#"))

    for prohibido in ("session_scope", "AgentExecution", "db.session"):
        assert prohibido not in codigo, f"F0 no puede tocar la DB ({prohibido})"
