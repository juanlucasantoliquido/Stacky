"""
tests/unit/test_sprint2_gates.py — Sprint 2: ENV gate + UI Map gate tests.

Valida los criterios de aceptación del Sprint 2 del roadmap:

  FP-1: policy=off  → ALLOW siempre, incluso con mismatch
  FP-2: policy=soft → WARN siempre, nunca BLOCKED (mismatch o source missing)
  FP-3: policy=hard → BLOCKED en mismatch
  FP-4: policy=hard → BLOCKED con reason=BUILD_UNVERIFIABLE cuando no hay source
  FP-5: policy=None (legacy) → BLOCKED en mismatch
  FP-6: policy=None (legacy) → WARN en dry-run sin source, BLOCKED en publish
  FP-7: deployment_fingerprint_checked event emitido en execution.jsonl
  FP-8: QA_UAT_DEPLOYMENT_POLICY env var leído correctamente

  UMR-1: resolve_ui_maps ALLOW cuando todos los UI maps existen en caché
  UMR-2: resolve_ui_maps BLOCKED UI_MAP_MISSING cuando falta al menos uno
  UMR-3: ui_map_resolution.json artefacto escrito en evidence_dir
  UMR-4: ui_map_resolution event emitido en execution.jsonl
  UMR-5: schema inválido en caché → tratado como missing
  UMR-6: pipeline bloquea con GEN UI_MAP_MISSING cuando falta UI map
  UMR-7: pipeline NO cae silenciosamente a FrmAgenda.aspx cuando screens=[]
  UMR-8: screen_detection_empty → BLOCKED PIP SCREEN_DETECTION_EMPTY
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_TOOL_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_TOOL_DIR))

os.environ.setdefault("STACKY_LLM_BACKEND", "mock")
os.environ.setdefault("QA_UAT_SKIP_SMOKE", "true")

_FIXTURES = Path(__file__).parent.parent / "fixtures"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_fp_result(decision: str, reason: str, matched: bool = False):
    """Build a minimal DeploymentFingerprintResult."""
    from deployment_fingerprint import DeploymentFingerprintResult
    return DeploymentFingerprintResult(
        matched=matched,
        source="manual_config" if matched else "unavailable",
        expected={"build_id": "Task-120-v1"},
        active={"build_id": "Task-119-v3"} if not matched else {"build_id": "Task-120-v1"},
        decision=decision,
        category="ENV" if decision == "BLOCKED" else None,
        reason=reason,
        skipped=False,
        elapsed_ms=10,
        artifact_path=None,
    )


def _write_valid_ui_map(cache_dir: Path, screen: str) -> None:
    """Write a minimal valid UI map JSON to cache_dir."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    ui_map = {
        "ok": True,
        "screen": screen,
        "schema_version": "ui_map/1.1",
        "elements": [
            {"alias_semantic": "btn_guardar", "tag": "button", "is_decorative": False}
        ],
    }
    (cache_dir / f"{screen}.json").write_text(
        json.dumps(ui_map, ensure_ascii=False), encoding="utf-8"
    )


# ══════════════════════════════════════════════════════════════════════════════
# FP — Deployment fingerprint policy tests
# ══════════════════════════════════════════════════════════════════════════════

class TestFingerprintPolicy:
    """Tests for QA_UAT_DEPLOYMENT_POLICY=off|soft|hard."""

    def _check(self, policy: str, expected: dict, source_available: bool,
               match: bool = False, mode: str = "dry-run"):
        """Run check_deployment_fingerprint with mocked probe results."""
        from deployment_fingerprint import check_deployment_fingerprint

        active = expected.copy() if match else {"build_id": "wrong-build"}
        source = "manual_config" if source_available else "unavailable"
        active_data = active if source_available else {}

        with patch(
            "deployment_fingerprint._probe_sources",
            return_value=(active_data, source, ""),
        ):
            result = check_deployment_fingerprint(
                ticket_id=120,
                expected=expected,
                base_url="http://localhost/AgendaWeb/",
                mode=mode,
                policy=policy,
            )
        return result

    def test_policy_off_allows_even_mismatch(self):
        """policy=off → ALLOW regardless of mismatch."""
        result = self._check("off", {"build_id": "Task-120-v1"},
                             source_available=True, match=False)
        assert result.decision == "ALLOW"
        assert result.reason == "POLICY_OFF"

    def test_policy_off_allows_no_source(self):
        """policy=off → ALLOW regardless of missing source."""
        result = self._check("off", {"build_id": "Task-120-v1"},
                             source_available=False, match=False)
        assert result.decision == "ALLOW"

    def test_policy_soft_warns_on_mismatch(self):
        """policy=soft → WARN (not BLOCKED) on mismatch."""
        result = self._check("soft", {"build_id": "Task-120-v1"},
                             source_available=True, match=False)
        assert result.decision == "WARN"
        assert result.reason == "DEPLOYMENT_MISMATCH"

    def test_policy_soft_warns_on_missing_source(self):
        """policy=soft → WARN (not BLOCKED) when no source available."""
        result = self._check("soft", {"build_id": "Task-120-v1"},
                             source_available=False)
        assert result.decision == "WARN"

    def test_policy_hard_blocks_on_mismatch(self):
        """policy=hard → BLOCKED on build mismatch."""
        result = self._check("hard", {"build_id": "Task-120-v1"},
                             source_available=True, match=False)
        assert result.decision == "BLOCKED"
        assert result.reason == "DEPLOYMENT_MISMATCH"
        assert result.category == "ENV"

    def test_policy_hard_blocks_build_unverifiable(self):
        """policy=hard → BLOCKED with BUILD_UNVERIFIABLE when no source available."""
        result = self._check("hard", {"build_id": "Task-120-v1"},
                             source_available=False)
        assert result.decision == "BLOCKED"
        assert result.reason == "BUILD_UNVERIFIABLE"
        assert result.category == "ENV"

    def test_policy_hard_allows_match(self):
        """policy=hard → ALLOW on exact match."""
        result = self._check("hard", {"build_id": "Task-120-v1"},
                             source_available=True, match=True)
        assert result.decision == "ALLOW"
        assert result.reason is None

    def test_legacy_blocks_mismatch_always(self):
        """policy=None (legacy) → BLOCKED on any mismatch."""
        result = self._check(None, {"build_id": "Task-120-v1"},
                             source_available=True, match=False)
        assert result.decision == "BLOCKED"

    def test_legacy_dryrun_warns_on_missing_source(self):
        """policy=None + dry-run → WARN when source unavailable."""
        result = self._check(None, {"build_id": "Task-120-v1"},
                             source_available=False, mode="dry-run")
        assert result.decision == "WARN"

    def test_legacy_publish_blocks_on_missing_source(self):
        """policy=None + publish → BLOCKED when source unavailable."""
        result = self._check(None, {"build_id": "Task-120-v1"},
                             source_available=False, mode="publish")
        assert result.decision == "BLOCKED"
        assert result.reason == "FINGERPRINT_SOURCE_MISSING"

    def test_env_var_policy_respected(self):
        """QA_UAT_DEPLOYMENT_POLICY env var is read when policy param is None."""
        from deployment_fingerprint import check_deployment_fingerprint
        with patch.dict(os.environ, {"QA_UAT_DEPLOYMENT_POLICY": "soft"}):
            with patch("deployment_fingerprint._probe_sources",
                       return_value=({"build_id": "wrong"}, "manual_config", "")):
                result = check_deployment_fingerprint(
                    ticket_id=120,
                    expected={"build_id": "correct"},
                    base_url="http://localhost/AgendaWeb/",
                )
        assert result.decision == "WARN", (
            f"Expected WARN from env var policy=soft, got {result.decision}"
        )

    def test_fp_artifact_written_when_evidence_dir_provided(self, tmp_path):
        """deployment_fingerprint.json artifact written when evidence_dir provided."""
        from deployment_fingerprint import check_deployment_fingerprint
        with patch("deployment_fingerprint._probe_sources",
                   return_value=({"build_id": "Task-120-v1"}, "manual_config", "")):
            result = check_deployment_fingerprint(
                ticket_id=120,
                expected={"build_id": "Task-120-v1"},
                base_url="http://localhost/AgendaWeb/",
                policy="hard",
                evidence_dir=tmp_path,
                run_id=None,  # no run_id → artifact goes directly in evidence_dir
            )
        artifact = tmp_path / "deployment_fingerprint.json"
        assert artifact.is_file(), "deployment_fingerprint.json not written"
        data = json.loads(artifact.read_text(encoding="utf-8"))
        assert data["decision"] == "ALLOW"


# ══════════════════════════════════════════════════════════════════════════════
# UMR — UI Map Resolution gate tests
# ══════════════════════════════════════════════════════════════════════════════

class TestUiMapResolution:
    """Tests for ui_map_resolution.py gate."""

    def test_allow_when_all_maps_cached(self, tmp_path):
        """resolve_ui_maps → ALLOW when all screens have valid cached UI maps."""
        from ui_map_resolution import resolve_ui_maps
        cache_dir = tmp_path / "cache" / "ui_maps"
        _write_valid_ui_map(cache_dir, "FrmAgenda.aspx")
        _write_valid_ui_map(cache_dir, "FrmDetalleClie.aspx")
        with patch.dict(os.environ, {"QA_UAT_UI_MAP_CACHE_DIR": str(cache_dir)}):
            result = resolve_ui_maps(
                screens=["FrmAgenda.aspx", "FrmDetalleClie.aspx"],
                evidence_dir=tmp_path / "evidence",
            )
        assert result["ok"] is True
        assert result["decision"] == "ALLOW"
        assert result["missing_screens"] == []

    def test_blocked_when_map_missing(self, tmp_path):
        """resolve_ui_maps → BLOCKED UI_MAP_MISSING when cache absent."""
        from ui_map_resolution import resolve_ui_maps
        cache_dir = tmp_path / "cache" / "ui_maps"
        _write_valid_ui_map(cache_dir, "FrmAgenda.aspx")
        # FrmDetalleClie.aspx intentionally NOT created
        with patch.dict(os.environ, {"QA_UAT_UI_MAP_CACHE_DIR": str(cache_dir)}):
            result = resolve_ui_maps(
                screens=["FrmAgenda.aspx", "FrmDetalleClie.aspx"],
                evidence_dir=tmp_path / "evidence",
            )
        assert result["ok"] is False
        assert result["decision"] == "BLOCKED"
        assert result["reason"] == "UI_MAP_MISSING"
        assert "FrmDetalleClie.aspx" in result["missing_screens"]

    def test_artifact_written(self, tmp_path):
        """ui_map_resolution.json artifact must be written to evidence_dir."""
        from ui_map_resolution import resolve_ui_maps
        cache_dir = tmp_path / "cache" / "ui_maps"
        evidence_dir = tmp_path / "evidence"
        _write_valid_ui_map(cache_dir, "FrmAgenda.aspx")
        with patch.dict(os.environ, {"QA_UAT_UI_MAP_CACHE_DIR": str(cache_dir)}):
            result = resolve_ui_maps(
                screens=["FrmAgenda.aspx"],
                evidence_dir=evidence_dir,
            )
        artifact = evidence_dir / "ui_map_resolution.json"
        assert artifact.is_file(), "ui_map_resolution.json not written"
        data = json.loads(artifact.read_text(encoding="utf-8"))
        assert data["decision"] == "ALLOW"
        assert result["artifact_path"] is not None

    def test_event_emitted(self, tmp_path):
        """ui_map_resolution event must be emitted to exec_logger."""
        from ui_map_resolution import resolve_ui_maps
        cache_dir = tmp_path / "cache" / "ui_maps"
        _write_valid_ui_map(cache_dir, "FrmAgenda.aspx")
        mock_logger = MagicMock()
        with patch.dict(os.environ, {"QA_UAT_UI_MAP_CACHE_DIR": str(cache_dir)}):
            resolve_ui_maps(
                screens=["FrmAgenda.aspx"],
                exec_logger=mock_logger,
            )
        mock_logger.event.assert_called_once()
        call_args = mock_logger.event.call_args
        assert call_args[0][0] == "ui_map_resolution"
        event_data = call_args[0][1]
        assert event_data["decision"] == "ALLOW"

    def test_invalid_schema_treated_as_missing(self, tmp_path):
        """Cache file with invalid schema_version is treated as missing."""
        from ui_map_resolution import resolve_ui_maps
        cache_dir = tmp_path / "cache" / "ui_maps"
        cache_dir.mkdir(parents=True, exist_ok=True)
        bad_map = {"schema_version": "unknown/2.0", "elements": []}
        (cache_dir / "FrmAgenda.aspx.json").write_text(
            json.dumps(bad_map), encoding="utf-8"
        )
        with patch.dict(os.environ, {"QA_UAT_UI_MAP_CACHE_DIR": str(cache_dir)}):
            result = resolve_ui_maps(
                screens=["FrmAgenda.aspx"],
                evidence_dir=tmp_path / "evidence",
            )
        assert result["decision"] == "BLOCKED"
        assert "FrmAgenda.aspx" in result["missing_screens"]

    def test_human_action_required_when_blocked(self, tmp_path):
        """human_action_required must be set when UI map is missing."""
        from ui_map_resolution import resolve_ui_maps
        cache_dir = tmp_path / "cache" / "ui_maps"
        cache_dir.mkdir(parents=True, exist_ok=True)
        with patch.dict(os.environ, {"QA_UAT_UI_MAP_CACHE_DIR": str(cache_dir)}):
            result = resolve_ui_maps(screens=["FrmDetalleClie.aspx"])
        assert result["human_action_required"] is not None
        assert "ui_map_builder.py" in result["human_action_required"]


# ══════════════════════════════════════════════════════════════════════════════
# Pipeline integration tests
# ══════════════════════════════════════════════════════════════════════════════

class TestPipelineSprintTwoGates:
    """Pipeline-level tests for Sprint 2 gates."""

    def _ticket(self, screen: str = "FrmDetalleClie.aspx") -> dict:
        return {
            "ok": True,
            "ticket_id": 122,
            "ticket": {"id": 122, "title": "Test Sprint 2"},
            "description_md": f"Verificar funcionalidad en {screen}",
            "plan_pruebas": [],
        }

    def test_pipeline_blocks_ui_map_missing(self, tmp_path):
        """Pipeline must return BLOCKED GEN UI_MAP_MISSING when UI map absent."""
        import qa_uat_pipeline as qp
        import execution_logger as el

        mock_pf = MagicMock()
        mock_pf.ok = True
        mock_pf.verdict = "PASS"
        mock_pf.reason = None
        mock_pf.base_url = "http://localhost"

        # Simulate empty cache dir — no UI maps
        cache_dir = tmp_path / "cache" / "ui_maps"
        cache_dir.mkdir(parents=True, exist_ok=True)

        with patch.object(qp, "_TOOL_ROOT", tmp_path), \
             patch("environment_preflight.run_environment_preflight", return_value=mock_pf), \
             patch("deployment_fingerprint.check_deployment_fingerprint", side_effect=ImportError), \
             patch("smoke_path_checker.run_smoke_path", side_effect=ImportError), \
             patch("uat_ticket_reader.run", return_value=self._ticket()), \
             patch("quality_intake.run_quality_intake", side_effect=ImportError), \
             patch("screen_detector.detect_screens_and_persist") as mock_detect, \
             patch.dict(os.environ, {
                 "QA_UAT_UI_MAP_CACHE_DIR": str(cache_dir),
                 "AGENDA_WEB_USER": "test_user",
                 "AGENDA_WEB_PASS": "test_pass",
                 "QA_UAT_DEPLOYMENT_POLICY": "off",
             }):

            mock_detect_result = MagicMock()
            mock_detect_result.selected_screens = ["FrmDetalleClie.aspx"]
            mock_detect_result.blocked = False
            mock_detect_result.block_reason = None
            mock_detect_result.confidence = 0.95
            mock_detect_result.fallback_used = False
            mock_detect_result.ambiguous = False
            mock_detect_result.artifact_path = None
            mock_detect_result.to_dict.return_value = {
                "selected_screens": ["FrmDetalleClie.aspx"],
                "blocked": False,
            }
            mock_detect.return_value = mock_detect_result

            result = qp.run(ticket_id=122, mode="dry-run", verbose=False)

        with el._registry_lock:
            el._registry.clear()

        assert result.get("verdict") == "BLOCKED", (
            f"Expected BLOCKED, got {result.get('verdict')!r}"
        )
        assert result.get("category") == "GEN", (
            f"Expected GEN, got {result.get('category')!r}"
        )
        assert result.get("reason") == "UI_MAP_MISSING", (
            f"Expected UI_MAP_MISSING, got {result.get('reason')!r}"
        )
        assert result.get("failed_stage") == "ui_map"

    def test_pipeline_blocks_screen_detection_empty(self, tmp_path):
        """Pipeline must BLOCK PIP SCREEN_DETECTION_EMPTY — no silent FrmAgenda fallback."""
        import qa_uat_pipeline as qp
        import execution_logger as el

        mock_pf = MagicMock()
        mock_pf.ok = True
        mock_pf.verdict = "PASS"
        mock_pf.reason = None
        mock_pf.base_url = "http://localhost"

        with patch.object(qp, "_TOOL_ROOT", tmp_path), \
             patch("environment_preflight.run_environment_preflight", return_value=mock_pf), \
             patch("deployment_fingerprint.check_deployment_fingerprint", side_effect=ImportError), \
             patch("smoke_path_checker.run_smoke_path", side_effect=ImportError), \
             patch("uat_ticket_reader.run", return_value=self._ticket()), \
             patch("quality_intake.run_quality_intake", side_effect=ImportError), \
             patch("screen_detector.detect_screens_and_persist") as mock_detect, \
             patch.dict(os.environ, {
                 "AGENDA_WEB_USER": "test_user",
                 "AGENDA_WEB_PASS": "test_pass",
                 "QA_UAT_DEPLOYMENT_POLICY": "off",
             }):

            mock_detect_result = MagicMock()
            # Empty screens list + not blocked = the silent fallback scenario
            mock_detect_result.selected_screens = []
            mock_detect_result.blocked = False
            mock_detect_result.block_reason = None
            mock_detect_result.confidence = 0.0
            mock_detect_result.fallback_used = False
            mock_detect_result.ambiguous = False
            mock_detect_result.artifact_path = None
            mock_detect_result.to_dict.return_value = {"selected_screens": [], "blocked": False}
            mock_detect.return_value = mock_detect_result

            result = qp.run(ticket_id=122, mode="dry-run", verbose=False)

        with el._registry_lock:
            el._registry.clear()

        # Must NOT silently fall back to FrmAgenda.aspx — must BLOCK
        assert result.get("verdict") == "BLOCKED", (
            f"Expected BLOCKED, got {result.get('verdict')!r}. "
            "Pipeline should NOT fall back silently to FrmAgenda.aspx"
        )
        assert result.get("reason") == "SCREEN_DETECTION_EMPTY", (
            f"Expected SCREEN_DETECTION_EMPTY, got {result.get('reason')!r}"
        )

    def test_pipeline_uses_deployment_policy_from_env(self, tmp_path):
        """QA_UAT_DEPLOYMENT_POLICY=off skips fingerprint gate entirely."""
        import qa_uat_pipeline as qp
        import execution_logger as el

        mock_pf = MagicMock()
        mock_pf.ok = True
        mock_pf.verdict = "PASS"
        mock_pf.reason = None
        mock_pf.base_url = "http://localhost"

        with patch.object(qp, "_TOOL_ROOT", tmp_path), \
             patch.dict(os.environ, {
                 "QA_UAT_DEPLOYMENT_POLICY": "off",
                 "QA_UAT_EXPECTED_BUILD_ID": "Task-wrong-build",
             }), \
             patch("environment_preflight.run_environment_preflight", return_value=mock_pf), \
             patch("smoke_path_checker.run_smoke_path", side_effect=ImportError), \
             patch("uat_ticket_reader.run", return_value=self._ticket()), \
             patch.object(qp, "_run_pipeline_stages", return_value={
                 "ok": True, "verdict": "PASS", "ticket_id": 122,
                 "stages": {}, "elapsed_s": 0.1,
             }):
            result = qp.run(ticket_id=122, mode="dry-run", verbose=False)

        with el._registry_lock:
            el._registry.clear()

        # policy=off must not block even with a wrong build ID configured
        assert result.get("verdict") != "BLOCKED" or result.get("reason") not in (
            "DEPLOYMENT_MISMATCH", "BUILD_UNVERIFIABLE",
        ), (
            "policy=off should skip fingerprint gate — pipeline should not block "
            f"but got verdict={result.get('verdict')!r} reason={result.get('reason')!r}"
        )
