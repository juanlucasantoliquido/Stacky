"""tests/test_mg_verify.py — Plan 217 Batch 5, F7a (§8.2).

Valida `tools/migrar_mantis_gitlab/migrator_mg_verify.py`:
  - conteo exacto origen vs. migrado (§8.2.1).
  - marker duplicado detectado (§8.2.2).
  - muestreo determinista (seed fija) con mismatch inyectado a propósito
    (§8.2.4).
  - `passed=False` cuando hay cualquier gap/duplicado/mismatch.
  - `passed=True` en el caso limpio.
  - consolidación de fallbacks/usuarios/adjuntos ya calculados (§8.2.5).
"""
from __future__ import annotations

from tools.migrar_mantis_gitlab.migrator_mg_verify import (
    MgVerificationResult,
    verify_migration,
)


def _mapping_row(mantis_id: str, gitlab_iid: str, status: str = "done") -> dict:
    return {
        "mantis_issue_id": mantis_id,
        "gitlab_iid": gitlab_iid,
        "status": status,
    }


def _origin_issue(mantis_id: str, title: str, state: str, priority_label: str) -> dict:
    return {
        "mantis_issue_id": mantis_id,
        "title": title,
        "expected_gitlab_state": state,
        "expected_priority_label": priority_label,
    }


def _real_item(iid: str, title: str, state: str, labels: "list[str] | None" = None) -> dict:
    return {"iid": iid, "title": title, "state": state, "labels": labels or []}


# ── §8.2.1: conteo exacto ────────────────────────────────────────────────


def test_conteo_exacto_origen_vs_migrado_sin_gap():
    mapping_rows = [_mapping_row("1", "100"), _mapping_row("2", "101")]
    origin_issues = [
        _origin_issue("1", "t1", "opened", "priority::P1-critica"),
        _origin_issue("2", "t2", "opened", "priority::P1-critica"),
    ]
    real_items = {
        "100": _real_item("100", "t1", "opened", ["priority::P1-critica"]),
        "101": _real_item("101", "t2", "opened", ["priority::P1-critica"]),
    }

    result = verify_migration(
        mapping_rows, origin_issues, writer=None, real_items_by_iid=real_items,
        sample_rate=1.0, sample_min=2,
    )

    assert result.total_origin == 2
    assert result.total_migrated == 2
    assert result.count_gap == 0


def test_conteo_detecta_gap_cuando_faltan_issues_migrados():
    mapping_rows = [_mapping_row("1", "100")]  # solo 1 migrado
    origin_issues = [
        _origin_issue("1", "t1", "opened", "priority::P1-critica"),
        _origin_issue("2", "t2", "opened", "priority::P1-critica"),  # nunca migrado
    ]
    real_items = {"100": _real_item("100", "t1", "opened", ["priority::P1-critica"])}

    result = verify_migration(
        mapping_rows, origin_issues, writer=None, real_items_by_iid=real_items,
        sample_rate=1.0, sample_min=1,
    )

    assert result.total_origin == 2
    assert result.total_migrated == 1
    assert result.count_gap == 1
    assert result.passed is False


# ── §8.2.2: marker duplicado ─────────────────────────────────────────────


def test_marker_duplicado_detectado_cuando_dos_mantis_id_comparten_gitlab_iid():
    mapping_rows = [
        _mapping_row("1", "100"),
        _mapping_row("2", "100"),  # mismo gitlab_iid que el issue 1 -> bug
    ]
    origin_issues = [
        _origin_issue("1", "t1", "opened", "priority::P1-critica"),
        _origin_issue("2", "t2", "opened", "priority::P1-critica"),
    ]
    real_items = {"100": _real_item("100", "t1", "opened", ["priority::P1-critica"])}

    result = verify_migration(
        mapping_rows, origin_issues, writer=None, real_items_by_iid=real_items,
        sample_rate=1.0, sample_min=2,
    )

    assert len(result.duplicate_markers) == 1
    assert "gitlab_iid=100" in result.duplicate_markers[0]
    assert result.passed is False


def test_sin_markers_duplicados_en_caso_limpio():
    mapping_rows = [_mapping_row("1", "100"), _mapping_row("2", "101")]
    origin_issues = [
        _origin_issue("1", "t1", "opened", "priority::P1-critica"),
        _origin_issue("2", "t2", "opened", "priority::P1-critica"),
    ]
    real_items = {
        "100": _real_item("100", "t1", "opened", ["priority::P1-critica"]),
        "101": _real_item("101", "t2", "opened", ["priority::P1-critica"]),
    }

    result = verify_migration(
        mapping_rows, origin_issues, writer=None, real_items_by_iid=real_items,
        sample_rate=1.0, sample_min=2,
    )

    assert result.duplicate_markers == []


# ── §8.2.4: muestreo determinista con mismatch inyectado ────────────────


def test_muestreo_determinista_detecta_mismatch_inyectado():
    # 10 filas migradas, sample_rate=1.0 fuerza a samplear TODAS -> determinista
    # sin depender de qué toque el random.
    mapping_rows = [_mapping_row(str(i), str(100 + i)) for i in range(10)]
    origin_issues = [
        _origin_issue(str(i), f"title-{i}", "opened", "priority::P1-critica") for i in range(10)
    ]
    real_items = {
        str(100 + i): _real_item(str(100 + i), f"title-{i}", "opened", ["priority::P1-critica"])
        for i in range(10)
    }
    # Mismatch inyectado a propósito: el título real del issue "5" difiere.
    real_items["105"]["title"] = "title-CORROMPIDO"

    result = verify_migration(
        mapping_rows, origin_issues, writer=None, real_items_by_iid=real_items,
        sample_rate=1.0, sample_min=10, rng_seed=42,
    )

    assert len(result.sample_mismatches) == 1
    mismatch = result.sample_mismatches[0]
    assert mismatch["mantis_issue_id"] == "5"
    assert mismatch["gitlab_iid"] == "105"
    assert mismatch["mismatches"] == [
        {"field": "title", "expected": "title-5", "actual": "title-CORROMPIDO"}
    ]
    assert result.passed is False


def test_muestreo_es_determinista_entre_dos_corridas_con_misma_seed():
    mapping_rows = [_mapping_row(str(i), str(200 + i)) for i in range(30)]
    origin_issues = [
        _origin_issue(str(i), f"title-{i}", "opened", "priority::P1-critica") for i in range(30)
    ]
    real_items = {
        str(200 + i): _real_item(str(200 + i), f"title-{i}", "opened", ["priority::P1-critica"])
        for i in range(30)
    }

    kwargs = dict(sample_rate=0.1, sample_min=5, rng_seed=42)
    r1 = verify_migration(mapping_rows, origin_issues, writer=None, real_items_by_iid=real_items, **kwargs)
    r2 = verify_migration(mapping_rows, origin_issues, writer=None, real_items_by_iid=real_items, **kwargs)

    assert r1.sample_mismatches == r2.sample_mismatches == []


def test_mismatch_de_estado_y_prioridad_tambien_se_detectan():
    mapping_rows = [_mapping_row("1", "100")]
    origin_issues = [_origin_issue("1", "t1", "closed", "priority::P1-critica")]
    # real difiere en estado (opened, no closed) y en prioridad (label distinto)
    real_items = {"100": _real_item("100", "t1", "opened", ["priority::P3-baja"])}

    result = verify_migration(
        mapping_rows, origin_issues, writer=None, real_items_by_iid=real_items,
        sample_rate=1.0, sample_min=1,
    )

    fields = {fd["field"] for fd in result.sample_mismatches[0]["mismatches"]}
    assert fields == {"gitlab_state", "priority"}


# ── passed=True en caso completamente limpio ─────────────────────────────


def test_passed_true_en_caso_limpio_sin_gap_sin_duplicados_sin_mismatches():
    mapping_rows = [_mapping_row(str(i), str(300 + i)) for i in range(5)]
    origin_issues = [
        _origin_issue(str(i), f"title-{i}", "opened", "priority::P1-critica") for i in range(5)
    ]
    real_items = {
        str(300 + i): _real_item(str(300 + i), f"title-{i}", "opened", ["priority::P1-critica"])
        for i in range(5)
    }

    result = verify_migration(
        mapping_rows, origin_issues, writer=None, real_items_by_iid=real_items,
        sample_rate=1.0, sample_min=5,
    )

    assert result == MgVerificationResult(
        total_origin=5,
        total_migrated=5,
        count_gap=0,
        duplicate_markers=[],
        sample_mismatches=[],
        unmapped_fallbacks_used=[],
        users_fallback=[],
        attachments_skipped=[],
        passed=True,
    )


# ── §8.2.5: consolidación de eventos ya calculados (pass-through) ───────


def test_consolida_unmapped_fallbacks_users_fallback_y_attachments_skipped():
    mapping_rows = [_mapping_row("1", "100")]
    origin_issues = [_origin_issue("1", "t1", "opened", "priority::P1-critica")]
    real_items = {"100": _real_item("100", "t1", "opened", ["priority::P1-critica"])}

    unmapped_events = [{"mantis_issue_id": "1", "field": "category", "value": "raro", "fallback_used": "otros"}]
    user_fallback_events = [{"mantis_username": "jdoe", "email": "jdoe@example.com", "fallback": "unassigned"}]
    attachment_skip_events = [{"mantis_issue_id": "1", "filename": "big.zip", "size_mb": 120.5}]

    result = verify_migration(
        mapping_rows, origin_issues, writer=None, real_items_by_iid=real_items,
        sample_rate=1.0, sample_min=1,
        unmapped_events=unmapped_events,
        user_fallback_events=user_fallback_events,
        attachment_skip_events=attachment_skip_events,
    )

    assert result.unmapped_fallbacks_used == unmapped_events
    assert result.users_fallback == user_fallback_events
    assert result.attachments_skipped == attachment_skip_events
    # estos eventos NO afectan `passed` por sí solos (no son gap/duplicado/mismatch)
    assert result.passed is True


def test_eventos_ausentes_default_a_listas_vacias():
    mapping_rows = [_mapping_row("1", "100")]
    origin_issues = [_origin_issue("1", "t1", "opened", "priority::P1-critica")]
    real_items = {"100": _real_item("100", "t1", "opened", ["priority::P1-critica"])}

    result = verify_migration(
        mapping_rows, origin_issues, writer=None, real_items_by_iid=real_items,
        sample_rate=1.0, sample_min=1,
    )

    assert result.unmapped_fallbacks_used == []
    assert result.users_fallback == []
    assert result.attachments_skipped == []


# ── writer solo se usa si real_items_by_iid es None ─────────────────────


def test_usa_writer_fetch_open_items_solo_si_real_items_by_iid_es_none():
    class _FakeWriter:
        def __init__(self):
            self.calls = 0

        def fetch_open_items(self):
            self.calls += 1
            return [{"iid": "100", "title": "t1", "state": "opened", "labels": ["priority::P1-critica"]}]

    writer = _FakeWriter()
    mapping_rows = [_mapping_row("1", "100")]
    origin_issues = [_origin_issue("1", "t1", "opened", "priority::P1-critica")]

    result = verify_migration(
        mapping_rows, origin_issues, writer=writer, sample_rate=1.0, sample_min=1,
    )

    assert writer.calls == 1
    assert result.passed is True
