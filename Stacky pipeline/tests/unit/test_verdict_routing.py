"""Tests del routing por veredicto QA en pipeline_runner._parse_qa_verdict."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from pipeline_runner import _parse_qa_verdict, _parse_qa_issues


def _write_tester(folder, verdict_text: str, findings_block: str = ""):
    content = f"# TESTER\n\n## Veredicto\n{verdict_text}\n\n{findings_block}"
    (folder / "TESTER_COMPLETADO.md").write_text(content, encoding="utf-8")


class TestParseQaVerdict:
    def test_detecta_aprobado(self, tmp_path):
        _write_tester(tmp_path, "APROBADO")
        verdict, _ = _parse_qa_verdict(str(tmp_path))
        assert verdict == "APROBADO"

    def test_detecta_con_observaciones(self, tmp_path):
        findings = "## Observaciones\n- Falta validación de input vacío\n- No cubre caso nulo\n"
        _write_tester(tmp_path, "CON OBSERVACIONES", findings)
        verdict, findings_list = _parse_qa_verdict(str(tmp_path))
        assert verdict == "CON OBSERVACIONES"
        assert len(findings_list) >= 1

    def test_detecta_rechazado(self, tmp_path):
        findings = "## Rechazos\n- Error crítico: rompe integridad referencial\n"
        _write_tester(tmp_path, "RECHAZADO", findings)
        verdict, findings_list = _parse_qa_verdict(str(tmp_path))
        assert verdict == "RECHAZADO"
        assert len(findings_list) >= 1

    def test_sin_archivo_retorna_desconocido(self, tmp_path):
        verdict, findings_list = _parse_qa_verdict(str(tmp_path))
        assert verdict == "DESCONOCIDO"
        assert findings_list == []

    def test_distingue_rechazado_de_observaciones(self, tmp_path):
        # El fix clave: rechazado y con-observaciones no pueden ser indistinguibles.
        _write_tester(tmp_path, "RECHAZADO")
        v_rej, _ = _parse_qa_verdict(str(tmp_path))

        _write_tester(tmp_path, "CON OBSERVACIONES")
        v_obs, _ = _parse_qa_verdict(str(tmp_path))

        assert v_rej == "RECHAZADO"
        assert v_obs == "CON OBSERVACIONES"
        assert v_rej != v_obs


class TestParseQaIssuesBackCompat:
    """El wrapper legacy sigue devolviendo (bool, list)."""

    def test_aprobado_no_es_issue(self, tmp_path):
        _write_tester(tmp_path, "APROBADO")
        has_issues, _ = _parse_qa_issues(str(tmp_path))
        assert has_issues is False

    def test_rechazado_es_issue(self, tmp_path):
        _write_tester(tmp_path, "RECHAZADO")
        has_issues, _ = _parse_qa_issues(str(tmp_path))
        assert has_issues is True

    def test_observaciones_es_issue(self, tmp_path):
        _write_tester(tmp_path, "CON OBSERVACIONES")
        has_issues, _ = _parse_qa_issues(str(tmp_path))
        assert has_issues is True
