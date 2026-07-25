"""tests/test_mg_cli_integration.py — Plan 217 F9 (Batch 6, último batch de
código), §17 "Integración dry-run" (el criterio de aceptación más importante
del plan).

Ejercita el CLI real (`tools/migrar_mantis_gitlab/__main__.py`) invocando
`main(argv)` directamente (más rápido/controlable que un subproceso, mismo
criterio que sugiere el batch), con:
  - Un `origin_adapter` FAKE in-memory (3 issues, 1 relación padre-hijo),
    inyectado monkeypateando `__main__._build_origin_adapter` (función de
    módulo independiente, diseñada para esto).
  - `DryRunGitLabWriter` en todo momento (`--dry-run`) — NUNCA el real.
  - Un config de prueba completo, con rutas de `tmp_path` para
    `checkpoint_file`/`report_output_dir`/SQLite del mapeo.

Decisión de diseño (documentada, siguiendo la instrucción del batch): la
idempotencia entre corridas SEPARADAS del CLI (2 invocaciones distintas de
`main()`, cada una con su propia instancia nueva de `DryRunGitLabWriter`) la
da el MAPEO PERSISTIDO en SQLite (`mantis_gitlab_map`), NO el estado en
memoria de `DryRunGitLabWriter.simulated_ops` (que arranca vacío en cada
instanciación). Por eso los asserts de idempotencia leen el mapeo persistido
y `plan.skipped_at_plan`/`MgExecutionResult`, no `writer.simulated_ops` — la
idempotencia de bajo nivel de `execute_migration` (incluida la reanudación
tras un corte) ya está probada en `test_mg_executor.py`; acá se prueba que
el CLI, como orquestador end-to-end, preserva esa garantía entre corridas.

`options.verify_after_execute=False` en el config de prueba, a propósito:
`DryRunGitLabWriter.fetch_open_items()` sólo expone `iid`/`description`
(§10 del plan, simulación mínima) — no `title`/`state`/`labels` — así que el
muestreo campo-a-campo de `verify_migration` (`test_mg_verify.py`, que sí
cubre ese contrato con un `real_items_by_iid` completo) reportaría
mismatches espurios contra un writer simulado. Mantener `verify_after_execute`
apagado en este test mantiene el foco en plan/execute/idempotencia (el
criterio de aceptación de esta fase), sin mezclar un hallazgo tangencial de
fidelidad de `DryRunGitLabWriter`.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.migrar_mantis_gitlab import __main__ as mg_main
from tools.migrar_mantis_gitlab.config_loader import load_config
from tools.migrar_mantis_gitlab.migrator_mg_map import get_full_mapping, get_plan_snapshot, open_map_db


class _FakeOriginAdapter:
    """SOLO tiene métodos `fetch_*` — sin create_item/post_comment/etc. Si
    algún camino del CLI intentara escribir contra el origen, explotaría por
    `AttributeError` (misma invariante que `test_mg_core.py`)."""

    def __init__(self) -> None:
        self.issues = [
            {
                "id": 501,
                "project_id": 900,
                "summary": "Issue raiz sin padre",
                "status": "new",
                "priority": 40,  # high -> escala 2
                "description": "Descripcion del issue raiz.",
            },
            {
                "id": 502,
                "project_id": 900,
                "summary": "Issue hijo de 501",
                "status": "assigned",
                "priority": 50,  # urgent -> escala 1
                "description": "Descripcion del issue hijo.",
            },
            {
                "id": 503,
                "project_id": 900,
                "summary": "Issue independiente",
                "status": "resolved",
                "priority": 30,  # normal -> escala 3
                "description": "Descripcion del tercer issue.",
            },
        ]
        self._relationships_by_id = {502: [{"type": "child of", "target_issue_id": 501}]}

    def fetch_all_issues(self) -> "list[dict]":
        return self.issues

    def fetch_comments(self, issue_id: int) -> "list[dict]":
        return []

    def fetch_attachments(self, issue_id: int) -> "list[dict]":
        return []

    def fetch_relationships(self, issue_id: int) -> "list[dict]":
        return self._relationships_by_id.get(issue_id, [])

    def download_attachment_binary(self, file_id):
        raise AssertionError("este test no tiene adjuntos: no debe llamarse")


def _write_test_config(tmp_path: Path, *, project_path: str = "grupo-test/proyecto-test") -> str:
    checkpoint_file = str(tmp_path / "run_state" / "test_checkpoint.json")
    report_output_dir = str(tmp_path / "reports_root")
    config = {
        "$schema_version": "1.0",
        "origin": {
            "type": "mantis",
            "base_url": "https://mantis.fake.local/mantis",
            "project_ids": [900],
            "extraction_mode": "scraping",
            "auth": {
                "auth_file": str(tmp_path / "auth" / "mantis_auth.json"),
                "protocol": "rest",
            },
            "include_resolved_closed": True,
            "csv_export_fallback": True,
        },
        "destination": {
            "type": "gitlab",
            "base_url": "https://gitlab.fake.local",
            "project_path": project_path,
            "auth": {
                "auth_file": str(tmp_path / "auth" / "gitlab_auth.json"),
                "secret_backend": "auto",
            },
            "preserve_authorship_mode": "metadata_only",
            "epics_strategy": "auto",
        },
        "user_mapping": {"default_fallback": "unassigned", "map": {}},
        "field_mapping": {
            "status": {
                "new": {"gitlab_state": "opened", "label": "status::new"},
                "assigned": {"gitlab_state": "opened", "label": "status::assigned"},
                "resolved": {"gitlab_state": "closed", "label": "status::resolved"},
                "_unmapped_fallback": {"gitlab_state": "opened", "label": "status::sin_mapear"},
            },
            "priority": {
                "label_prefix": "priority::",
                "scale": {
                    "1": "P1-critica",
                    "2": "P2-alta",
                    "3": "P3-normal",
                    "4": "P4-baja",
                    "5": "P5-trivial",
                },
            },
            "severity": {"label_prefix": "severity::"},
            "category": {"label_prefix": "category::"},
            "tags": {"label_prefix": "tag::"},
            "version": {
                "target_version_as": "milestone",
                "fixed_in_version_as": "label:fixed_in::",
                "affects_version_as": "label:affects::",
            },
            "relationships": {
                "parent_child": "gitlab_epic_issue_link",
                "related_to": "relates_to",
            },
            "custom_fields": {"mode": "metadata_block"},
        },
        "options": {
            "dry_run": True,
            "batch_size": 25,
            "max_retries": 5,
            "retry_backoff_seconds": [2, 5, 15, 30, 60],
            "rate_limit_pause_on_429_seconds": 60,
            "attachments": {"max_size_mb": 50, "skip_if_over_limit": True, "download_temp_dir": None},
            "incremental": {
                "enabled": True,
                "since_field": "last_updated",
                "checkpoint_file": checkpoint_file,
            },
            # Ver docstring del módulo: apagado a propósito en este test.
            "verify_after_execute": False,
            "report_formats": ["markdown", "json"],
            "report_output_dir": report_output_dir,
        },
        "logging": {
            "level": "INFO",
            "file": str(tmp_path / "logs" / "mg_{run_id}.log"),
            "redact_secrets": True,
        },
    }
    config_path = tmp_path / "migration_config_test.json"
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(config_path)


@pytest.fixture
def fake_adapter(monkeypatch) -> _FakeOriginAdapter:
    adapter = _FakeOriginAdapter()
    monkeypatch.setattr(mg_main, "_build_origin_adapter", lambda config: adapter)
    return adapter


# ── plan: genera el plan completo, CERO escrituras ─────────────────────────


def test_plan_genera_plan_completo_con_las_3_ops_esperadas(tmp_path, fake_adapter):
    config_path = _write_test_config(tmp_path)

    exit_code = mg_main.main(["plan", "--config", config_path])
    assert exit_code == 0

    config = load_config(config_path)
    map_db_path = mg_main._resolve_map_db_path(config)
    conn = open_map_db(map_db_path)
    try:
        snapshot = get_plan_snapshot(conn, config.destination.project_path)
        assert snapshot is not None
        assert len(snapshot["plan_data"]["ops"]) == 3
        assert snapshot["plan_data"]["counts_by_type"] == {"create_item": 3}
        assert snapshot["plan_data"]["skipped_at_plan"] == 0

        # El plan aún no ejecutó nada: el mapeo local sigue vacío (ninguna
        # escritura real ni simulada ocurrió durante 'plan').
        assert get_full_mapping(conn, config.destination.project_path) == []
    finally:
        conn.close()


def test_plan_ordena_topologicamente_padre_antes_que_hijo(tmp_path, fake_adapter):
    config_path = _write_test_config(tmp_path)
    mg_main.main(["plan", "--config", config_path])

    config = load_config(config_path)
    conn = open_map_db(mg_main._resolve_map_db_path(config))
    try:
        snapshot = get_plan_snapshot(conn, config.destination.project_path)
        ids_en_orden = [op["mantis_issue_id"] for op in snapshot["plan_data"]["ops"]]
        # 501 y 503 no tienen padre (rank 0, orden estable); 502 tiene padre 501 (rank 1).
        assert ids_en_orden == ["501", "503", "502"]
    finally:
        conn.close()


# ── execute --dry-run: mismo camino de código, reporte [SIMULACRO] ────────


def test_execute_dry_run_produce_reporte_simulacro_en_disco(tmp_path, fake_adapter):
    config_path = _write_test_config(tmp_path)
    assert mg_main.main(["plan", "--config", config_path]) == 0

    exit_code = mg_main.main(["execute", "--config", config_path, "--dry-run"])
    assert exit_code == 0

    config = load_config(config_path)
    reports_dir = Path(config.options.report_output_dir)
    md_files = sorted(reports_dir.glob("*.md"))
    json_files = sorted(reports_dir.glob("*.json"))
    assert len(md_files) == 1
    assert len(json_files) == 1

    markdown = md_files[0].read_text(encoding="utf-8")
    assert "[SIMULACRO]" in markdown

    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["dry_run"] is True
    # NOTA: "issues_migrados" sale de MgVerificationResult.total_migrated, no
    # de la ejecución — con verify_after_execute=False (ver docstring del
    # módulo) queda en su default (0). Lo que sí refleja la ejecución real
    # (3 create_item simulados) es "operaciones_aplicadas_total".
    assert payload["summary"]["operaciones_aplicadas_total"] == 3
    assert payload["summary"]["operaciones_salteadas_idempotencia"] == 0
    assert payload["summary"]["operaciones_fallidas_total"] == 0

    # El mapeo quedó persistido en SQLite: los 3 issues terminaron "done"
    # con un gitlab_iid SIMULADO (prefijo "dryrun-", nunca un ID real).
    conn = open_map_db(mg_main._resolve_map_db_path(config))
    try:
        rows = {r["mantis_issue_id"]: r for r in get_full_mapping(conn, config.destination.project_path)}
        assert set(rows) == {"501", "502", "503"}
        assert all(r["status"] == "done" for r in rows.values())
        assert all(r["gitlab_iid"].startswith("dryrun-") for r in rows.values())
    finally:
        conn.close()


# ── idempotencia entre corridas separadas del CLI (mapeo persistido) ──────


def test_segunda_corrida_plan_mas_execute_dry_run_es_idempotente(tmp_path, fake_adapter, capsys):
    config_path = _write_test_config(tmp_path)

    # 1ra corrida completa: crea los 3 issues (simulados).
    assert mg_main.main(["plan", "--config", config_path]) == 0
    assert mg_main.main(["execute", "--config", config_path, "--dry-run"]) == 0
    capsys.readouterr()  # descarta stdout de la 1ra corrida

    # 2da corrida completa sobre el MISMO config/SQLite: 'plan' debe ver los
    # 3 issues como ya migrados (status=done) y no generar ops nuevas.
    assert mg_main.main(["plan", "--config", config_path]) == 0
    plan_stdout = capsys.readouterr().out
    assert "Saltados (ya migrados, status=done): 3" in plan_stdout

    assert mg_main.main(["execute", "--config", config_path, "--dry-run"]) == 0
    execute_stdout = capsys.readouterr().out
    # plan_migration ya excluyó los 3 issues "done" ANTES de que se
    # conviertan en ops (ver migrator_mg_core.plan_migration) — por eso acá
    # el contador de aplicadas/salteadas del EJECUTOR es 0/0 (el plan que le
    # llega está vacío), no "0 aplicadas / 3 salteadas". La garantía real de
    # "no se duplica nada" está en que el mapeo sigue con exactamente 3 filas
    # 'done' después de la 2da corrida (ver abajo), no en este contador.
    assert "Aplicadas: 0, salteadas (idempotencia): 0, fallidas: 0" in execute_stdout

    config = load_config(config_path)
    conn = open_map_db(mg_main._resolve_map_db_path(config))
    try:
        rows = get_full_mapping(conn, config.destination.project_path)
        assert len(rows) == 3
        assert all(r["status"] == "done" for r in rows)
    finally:
        conn.close()


# ── el fake adapter no expone métodos de escritura: dry-run real ──────────


def test_fake_adapter_no_tiene_metodos_de_escritura(fake_adapter):
    """Documenta la invariante que hace que este test de integración sea una
    prueba REAL de dry-run: si `plan`/`execute --dry-run` intentaran alguna
    vez escribir contra el ORIGEN (nunca deberían), explotarían por
    AttributeError contra este fake."""
    for attr in ("create_item", "post_comment", "upload_attachment", "link_attachment"):
        assert not hasattr(fake_adapter, attr)
