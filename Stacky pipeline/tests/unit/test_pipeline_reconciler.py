"""Tests del reconciliador del pipeline."""
import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from pipeline_reconciler import (
    derive_stage_from_folder,
    reconcile_ticket_entry,
    ReconcileResult,
    DerivedState,
)


# ── Helpers de fixture ─────────────────────────────────────────────────────────

def _touch(folder, name, content=""):
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        f.write(content)


# ── derive_stage_from_folder ───────────────────────────────────────────────────

class TestDeriveStageFromFolder:
    def test_folder_vacio_pendiente_pm(self, tmp_path):
        # Carpeta vacía → pendiente_pm pero SIN next_stage:
        # el reconciliador no debe auto-lanzar PM desde la nada (evita storm de arranque).
        ds = derive_stage_from_folder(str(tmp_path))
        assert ds.estado == "pendiente_pm"
        assert ds.next_stage is None

    def test_folder_no_existe(self, tmp_path):
        ds = derive_stage_from_folder(str(tmp_path / "no-existe"))
        assert ds.estado == "desconocido"
        assert ds.next_stage is None

    def test_pm_completado_solo(self, tmp_path):
        _touch(tmp_path, "PM_COMPLETADO.flag")
        ds = derive_stage_from_folder(str(tmp_path))
        assert ds.estado == "pm_completado"
        assert ds.next_stage == "dev"

    def test_dev_completado_sin_tester(self, tmp_path):
        _touch(tmp_path, "PM_COMPLETADO.flag")
        _touch(tmp_path, "DEV_COMPLETADO.md", "# done")
        ds = derive_stage_from_folder(str(tmp_path))
        assert ds.estado == "dev_completado"
        assert ds.next_stage == "tester"

    def test_tester_aprobado_es_completado(self, tmp_path):
        _touch(tmp_path, "DEV_COMPLETADO.md")
        _touch(tmp_path, "TESTER_COMPLETADO.md", "VEREDICTO: APROBADO\nTodo ok")
        ds = derive_stage_from_folder(str(tmp_path))
        assert ds.estado == "completado"
        assert ds.next_stage is None
        assert ds.qa_verdict == "APROBADO"

    def test_tester_con_observaciones_es_completado(self, tmp_path):
        _touch(tmp_path, "DEV_COMPLETADO.md")
        _touch(tmp_path, "TESTER_COMPLETADO.md", "VEREDICTO: CON OBSERVACIONES")
        ds = derive_stage_from_folder(str(tmp_path))
        assert ds.estado == "completado"
        assert ds.qa_verdict == "CON OBSERVACIONES"

    def test_tester_rechazado_bifurca_a_pm_revision(self, tmp_path):
        _touch(tmp_path, "DEV_COMPLETADO.md")
        _touch(tmp_path, "TESTER_COMPLETADO.md", "VEREDICTO: RECHAZADO\nBL-01: ...")
        ds = derive_stage_from_folder(str(tmp_path))
        assert ds.estado == "pm_revision"
        assert ds.next_stage == "pm"
        assert ds.qa_verdict == "RECHAZADO"

    def test_tester_rechazado_gana_aunque_diga_aprobado_antes(self, tmp_path):
        """Si el texto contiene ambos, RECHAZADO debe ganar."""
        _touch(tmp_path, "DEV_COMPLETADO.md")
        _touch(tmp_path, "TESTER_COMPLETADO.md",
               "Criterios aprobados: C1, C2\nVEREDICTO: RECHAZADO")
        ds = derive_stage_from_folder(str(tmp_path))
        assert ds.estado == "pm_revision"
        assert ds.qa_verdict == "RECHAZADO"

    def test_dev_error_manda_a_rework(self, tmp_path):
        """Escenario ticket 40: DEV_ERROR.flag tras desatascador."""
        _touch(tmp_path, "PM_COMPLETADO.flag")
        _touch(tmp_path, "DEV_COMPLETADO.md.prev")
        _touch(tmp_path, "TESTER_COMPLETADO.md.prev")
        _touch(tmp_path, "DEV_ERROR.flag", "BL-01: ...")
        ds = derive_stage_from_folder(str(tmp_path))
        assert ds.estado == "qa_rework"
        assert ds.next_stage == "dev"
        assert "DEV_ERROR.flag" in ds.evidence

    def test_bloqueo_humano_gana_a_todo(self, tmp_path):
        _touch(tmp_path, "PM_COMPLETADO.flag")
        _touch(tmp_path, "DEV_COMPLETADO.md")
        _touch(tmp_path, "TESTER_COMPLETADO.md", "VEREDICTO: APROBADO")
        _touch(tmp_path, "BLOQUEO_HUMANO.flag", "Requiere credenciales SAP")
        ds = derive_stage_from_folder(str(tmp_path))
        assert ds.estado == "bloqueo_humano"
        assert ds.next_stage is None

    def test_agente_en_curso_tiene_precedencia_sobre_completados(self, tmp_path):
        """Si hay un DEV_AGENTE_EN_CURSO.flag, el ticket está corriendo, no completado."""
        _touch(tmp_path, "PM_COMPLETADO.flag")
        _touch(tmp_path, "DEV_AGENTE_EN_CURSO.flag")
        ds = derive_stage_from_folder(str(tmp_path))
        assert ds.estado == "dev_en_proceso"
        assert ds.next_stage is None   # ya corriendo, no lanzar

    def test_tester_error_sin_tester_completado(self, tmp_path):
        _touch(tmp_path, "DEV_COMPLETADO.md")
        _touch(tmp_path, "TESTER_ERROR.flag", "timeout")
        ds = derive_stage_from_folder(str(tmp_path))
        assert ds.estado == "error_tester"
        assert ds.next_stage == "tester"


# ── reconcile_ticket_entry ─────────────────────────────────────────────────────

class TestReconcileTicketEntry:
    def test_coherente_no_cambia_nada(self, tmp_path):
        _touch(tmp_path, "PM_COMPLETADO.flag")
        _touch(tmp_path, "DEV_COMPLETADO.md")
        _touch(tmp_path, "TESTER_COMPLETADO.md", "APROBADO")
        entry = {"estado": "completado"}
        r = reconcile_ticket_entry("42", str(tmp_path), entry)
        assert r.coherent is True
        assert r.needs_sync is False
        assert r.launch_stage is None

    def test_bug_42_post_unstick(self, tmp_path):
        """
        Ticket 40/42: state.json dice 'completado' pero DEV_ERROR.flag en folder.
        Debe sincronizar a qa_rework y disparar DEV.
        """
        _touch(tmp_path, "PM_COMPLETADO.flag")
        _touch(tmp_path, "DEV_COMPLETADO.md.prev")
        _touch(tmp_path, "TESTER_COMPLETADO.md.prev")
        _touch(tmp_path, "DEV_ERROR.flag", "BL-01")
        entry = {
            "estado": "completado",
            "completado_at": "2026-04-18T23:19:12",
            # last_invoke muy antiguo — fuera del debounce
            "last_invoke": {"at": "2026-04-18T23:15:00"},
        }
        r = reconcile_ticket_entry("42", str(tmp_path), entry,
                                    now=datetime(2026, 4, 19, 15, 0, 0))
        assert r.coherent is False
        assert r.needs_sync is True
        assert r.synthetic_state == "qa_rework"
        assert r.launch_stage == "dev"

    def test_debounce_previene_relanzamiento_rapido(self, tmp_path):
        """Si hubo invocación hace < 45s, NO relanzar aunque haya divergencia."""
        _touch(tmp_path, "DEV_ERROR.flag", "fail")
        _touch(tmp_path, "PM_COMPLETADO.flag")
        entry = {
            "estado": "completado",
            "last_invoke": {"at": datetime.now().isoformat()},
        }
        r = reconcile_ticket_entry("x", str(tmp_path), entry)
        # synthetic_state se marca pero launch_stage NO (debounce)
        assert r.needs_sync is True
        assert r.launch_stage is None
        assert any("debounce" in w for w in r.warnings)

    def test_stale_en_proceso_sin_en_curso_flag(self, tmp_path):
        """Ticket en dev_en_proceso sin DEV_AGENTE_EN_CURSO.flag y > stale_min → stale."""
        _touch(tmp_path, "PM_COMPLETADO.flag")
        # Nada más — el dev supuestamente está corriendo pero el flag no está
        entry = {
            "estado": "dev_en_proceso",
            "dev_en_proceso_at": (datetime.now() - timedelta(minutes=30)).isoformat(),
        }
        r = reconcile_ticket_entry("x", str(tmp_path), entry)
        assert r.is_stale is True
        assert r.stale_reason

    def test_agente_corriendo_legit_no_marca_stale(self, tmp_path):
        _touch(tmp_path, "PM_COMPLETADO.flag")
        _touch(tmp_path, "DEV_AGENTE_EN_CURSO.flag")
        entry = {
            "estado": "dev_en_proceso",
            "dev_en_proceso_at": (datetime.now() - timedelta(minutes=3)).isoformat(),
        }
        r = reconcile_ticket_entry("x", str(tmp_path), entry)
        assert r.is_stale is False

    def test_bloqueo_humano_no_dispara_etapa(self, tmp_path):
        _touch(tmp_path, "BLOQUEO_HUMANO.flag")
        entry = {"estado": "dev_completado"}
        r = reconcile_ticket_entry("x", str(tmp_path), entry)
        assert r.launch_stage is None
        assert r.synthetic_state == "bloqueo_humano"

    def test_stored_pm_revision_folder_completado_no_fuerza_sync(self, tmp_path):
        """
        pm_revision es un estado bifurcado post-tester. El folder sigue teniendo
        TESTER_COMPLETADO.md con RECHAZADO pero el watcher ya movió a pm_revision.
        NO debemos pisar ese estado con 'pm_revision' derivado (son lo mismo).
        """
        _touch(tmp_path, "DEV_COMPLETADO.md")
        _touch(tmp_path, "TESTER_COMPLETADO.md", "VEREDICTO: RECHAZADO\nBL-01")
        entry = {"estado": "pm_revision"}
        r = reconcile_ticket_entry("x", str(tmp_path), entry)
        # derived devuelve "pm_revision" → coherente
        assert r.coherent is True

    def test_folder_inexistente_no_explota(self, tmp_path):
        entry = {"estado": "dev_en_proceso"}
        r = reconcile_ticket_entry("x", str(tmp_path / "nope"), entry)
        assert r.coherent is True
        assert "folder_no_existe" in r.warnings


class TestCoherentWith:
    def test_equivalencias(self):
        from pipeline_reconciler import coherent_with
        assert coherent_with("pm_revision", "pm_revision_completado") is True
        assert coherent_with("dev_completado", "dev_rework_completado") is True
        assert coherent_with("completado", "completado") is True
        assert coherent_with("completado", "dev_completado") is False
