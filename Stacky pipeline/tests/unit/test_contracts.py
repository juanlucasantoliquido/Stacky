"""Tests unitarios para pipeline_contracts.py — contratos Pydantic entre etapas."""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pydantic import ValidationError
from pipeline_contracts import PMOutputContract, DEVOutputContract, QAOutputContract


class TestPMOutputContract:
    def test_valid_pm_output(self):
        contract = PMOutputContract(
            incidente_lines=10, analisis_lines=15, arquitectura_lines=8,
            tareas_lines=10, has_pending_tasks=True, placeholders_count=0,
            files_with_code_refs=["Batch/Negocio/EjemploDalc.cs"]
        )
        assert contract.placeholders_count == 0

    def test_rechaza_con_placeholders(self):
        with pytest.raises(ValidationError) as exc:
            PMOutputContract(
                incidente_lines=10, analisis_lines=15, arquitectura_lines=8,
                tareas_lines=10, has_pending_tasks=True, placeholders_count=3,
                files_with_code_refs=["Batch/Negocio/EjemploDalc.cs"]
            )
        assert "placeholder" in str(exc.value).lower()

    def test_empty_files_allowed(self):
        contract = PMOutputContract(
            incidente_lines=10, analisis_lines=15, arquitectura_lines=8,
            tareas_lines=10, has_pending_tasks=False, placeholders_count=0,
            files_with_code_refs=[]
        )
        assert contract.files_with_code_refs == []


class TestDEVOutputContract:
    def test_valid_dev_output(self):
        contract = DEVOutputContract(
            files_modified=["Batch/Negocio/PagosDalc.cs"],
            pending_tasks=0,
            build_result="ok"
        )
        assert contract.pending_tasks == 0

    def test_rechaza_sin_archivos_modificados(self):
        with pytest.raises(ValidationError):
            DEVOutputContract(files_modified=[], pending_tasks=0)

    def test_rechaza_con_tareas_pendientes(self):
        with pytest.raises(ValidationError):
            DEVOutputContract(
                files_modified=["Batch/Negocio/PagosDalc.cs"],
                pending_tasks=2
            )

    def test_build_result_optional(self):
        contract = DEVOutputContract(
            files_modified=["file.cs"], pending_tasks=0
        )
        assert contract.build_result is None


class TestQAOutputContract:
    def test_valid_qa_aprobado(self):
        contract = QAOutputContract(
            verdict="APROBADO", cases_count=5, findings=[]
        )
        assert contract.verdict == "APROBADO"

    def test_valid_qa_con_observaciones(self):
        contract = QAOutputContract(
            verdict="CON OBSERVACIONES", cases_count=3,
            findings=["Error en validación nula"]
        )
        assert len(contract.findings) == 1

    def test_rechaza_veredicto_invalido(self):
        with pytest.raises(ValidationError):
            QAOutputContract(verdict="MAYBE", cases_count=1, findings=[])

    def test_rechaza_sin_casos(self):
        with pytest.raises(ValidationError):
            QAOutputContract(verdict="APROBADO", cases_count=0, findings=[])

    def test_rechazado_es_valido(self):
        contract = QAOutputContract(
            verdict="RECHAZADO", cases_count=2,
            findings=["Bug crítico", "Regresión"]
        )
        assert contract.verdict == "RECHAZADO"
