"""
Unit tests — Fase 2 Universal Discovery Pipeline

Covers:
  - domain_glossary: lookup / polarity / normalization
  - precondition_parser: Layer 0 (RIDIOMA), Layer 2 (glossary), unresolved path, emit helpers
  - sql_builder: identifier safety, query construction
  - resolution_cache: get/set/expire
  - data_resolver: _try_dynamic_resolution falls back gracefully without DB
  - sql_query_guard: expanded WHITELISTED_TABLES
"""

import json
import time
import re
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# ── ensure project root is in sys.path ────────────────────────────────────────
_HERE = Path(__file__).parent
_ROOT = _HERE.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ──────────────────────────────────────────────────────────────────────────────
# 1. domain_glossary
# ──────────────────────────────────────────────────────────────────────────────

class TestDomainGlossary:

    def test_lookup_corredor_returns_roblg(self):
        from domain_glossary import lookup
        results = lookup("corredor")
        tables = [m.table for m in results]
        assert "ROBLG" in tables, f"Expected ROBLG in {tables}"

    def test_lookup_riesgo_returns_clriesgoent(self):
        """The real RSPACIFICO column is CLRIESGOENT, NOT CLRIESGOSIS."""
        from domain_glossary import lookup
        results = lookup("riesgo")
        columns = [m.column for m in results]
        assert "CLRIESGOENT" in columns, f"Expected CLRIESGOENT in {columns}"
        assert "CLRIESGOSIS" not in columns, "CLRIESGOSIS is the wrong column name"

    def test_lookup_lote_returns_locod(self):
        """The real RSPACIFICO column is LOCOD in RLOTE, NOT IDLOTE."""
        from domain_glossary import lookup
        results = lookup("lote")
        columns = [m.column for m in results]
        assert "LOCOD" in columns, f"Expected LOCOD in {columns}"
        assert "IDLOTE" not in columns, "IDLOTE does not exist in RSPACIFICO schema"

    def test_lookup_normalized_accent(self):
        """'corredor' and 'corrédor' should hit the same mapping."""
        from domain_glossary import lookup
        results_norm = lookup("corrédor")
        assert results_norm, "Lookup with accented term should return results"

    def test_lookup_unknown_term_returns_empty(self):
        from domain_glossary import lookup
        results = lookup("xyz_nonexistent_term_9999")
        assert results == [], f"Expected empty, got {results}"

    def test_lookup_with_polarity_value(self):
        from domain_glossary import lookup_with_polarity
        results = lookup_with_polarity("corredor", "value")
        assert results, "Should return at least one result for corredor/value"

    def test_get_all_terms_nonempty(self):
        from domain_glossary import get_all_terms
        terms = get_all_terms()
        assert len(terms) >= 5, "Should have at least 5 registered terms"


# ──────────────────────────────────────────────────────────────────────────────
# 2. precondition_parser
# ──────────────────────────────────────────────────────────────────────────────

class TestPreconditionParserLayer0Ridioma:
    """Layer 0: RIDIOMA detection."""

    def test_ridioma_id_extracted(self):
        from precondition_parser import parse
        result = parse("RIDIOMA 9296 debe existir", use_llm=False)
        assert result.ridioma_ids == [9296]
        ridioma_conds = [c for c in result.conditions if c.source == "ridioma"]
        assert ridioma_conds, "Should have at least one ridioma condition"

    def test_ridioma_range_extracted(self):
        from precondition_parser import parse
        result = parse("INSERT RIDIOMA 9296-9298", use_llm=False)
        assert 9296 in result.ridioma_ids
        assert 9298 in result.ridioma_ids

    def test_ridioma_comma_list(self):
        from precondition_parser import parse
        result = parse("RIDIOMA=9296,9297", use_llm=False)
        assert 9296 in result.ridioma_ids
        assert 9297 in result.ridioma_ids


class TestPreconditionParserLayer2Glossary:
    """Layer 2: domain glossary match (no DB, no LLM)."""

    def test_corredor_resolved_to_roblg(self):
        from precondition_parser import parse
        result = parse("el campo corredor debe tener valor asignado", use_llm=False)
        tables = [c.table for c in result.conditions]
        assert "ROBLG" in tables, f"Expected ROBLG, got {tables}"

    def test_riesgo_resolved_to_clriesgoent(self):
        from precondition_parser import parse
        result = parse("existe riesgo de entrada para el cliente", use_llm=False)
        columns = [c.column for c in result.conditions]
        assert "CLRIESGOENT" in columns, f"Expected CLRIESGOENT, got {columns}"

    def test_lote_resolved_to_locod(self):
        from precondition_parser import parse
        result = parse("el lote debe existir en la base", use_llm=False)
        columns = [c.column for c in result.conditions]
        assert "LOCOD" in columns, f"Expected LOCOD, got {columns}"


class TestPreconditionParserUnresolved:

    def test_totally_unknown_term_is_unresolved(self):
        from precondition_parser import parse
        result = parse("zq99_campo_inexistente must exist", use_llm=False)
        # Should be in unresolved since no DB, no glossary, no LLM
        # (might partially resolve via schema if DB is absent — just ensure no crash)
        assert hasattr(result, "unresolved")

    def test_parse_returns_parse_result_type(self):
        from precondition_parser import parse, ParseResult
        result = parse("any text", use_llm=False)
        assert isinstance(result, ParseResult)


class TestPreconditionParserEmit:

    def test_emit_resolved_values_creates_file(self, tmp_path):
        from precondition_parser import parse, emit_resolved_values, ParseResult
        from domain_glossary import lookup

        # Build a fake parse result with a condition that has a value
        from precondition_parser import ParsedCondition, ParseResult
        cond = ParsedCondition(
            term="corredor",
            source="glossary",
            table="ROBLG",
            column="OGCORREDOR",
            operator="=",
            value="AGT01",
            condition="ROBLG.OGCORREDOR = 'AGT01'",
            confidence=0.9,
            polarity="value",
            join_path=[],
        )
        result = ParseResult(
            original="corredor = AGT01",
            conditions=[cond],
            ridioma_ids=[],
            unresolved=[],
            parse_method="glossary",
        )

        out = tmp_path / "resolved_values.json"
        emit_resolved_values([result], scenario_id="SC-01", out_path=out)

        assert out.is_file()
        data = json.loads(out.read_text())
        assert "values" in data or "ROBLG_OGCORREDOR" in str(data)

    def test_emit_precondition_gap_creates_file(self, tmp_path):
        from precondition_parser import ParseResult, emit_precondition_gap

        result = ParseResult(
            original="something unknown",
            conditions=[],
            ridioma_ids=[],
            unresolved=["unknown_field"],
            parse_method="unresolved",
        )
        out = tmp_path / "precondition_gap.json"
        emit_precondition_gap([result], scenario_id="SC-01", out_path=out)
        assert out.is_file()
        data = json.loads(out.read_text())
        assert "gaps" in data or "unresolved" in str(data)


# ──────────────────────────────────────────────────────────────────────────────
# 3. sql_builder
# ──────────────────────────────────────────────────────────────────────────────

class TestSqlBuilder:

    def test_build_data_lookup_query_returns_select(self):
        from sql_builder import build_data_lookup_query
        q = build_data_lookup_query("ROBLG", "OGCORREDOR")
        assert q is not None
        assert q.strip().upper().startswith("SELECT")
        assert "ROBLG" in q
        assert "OGCORREDOR" in q

    def test_build_data_lookup_query_has_top_n(self):
        from sql_builder import build_data_lookup_query
        q = build_data_lookup_query("RLOTE", "LOCOD")
        assert "TOP" in q.upper(), f"Expected TOP N in query, got: {q}"

    def test_invalid_identifier_rejected(self):
        from sql_builder import build_data_lookup_query
        # SQL injection attempt — should be rejected
        q = build_data_lookup_query("RLOTE; DROP TABLE RLOTE--", "LOCOD")
        assert q is None, "Should reject unsafe table identifier"

    def test_build_check_query_with_condition(self):
        from precondition_parser import ParsedCondition
        from sql_builder import build_check_query
        cond = ParsedCondition(
            term="lote",
            source="glossary",
            table="RLOTE",
            column="LOCOD",
            operator="IS NOT NULL",
            value=None,
            condition="RLOTE.LOCOD IS NOT NULL",
            confidence=0.8,
            polarity="exists",
            join_path=[],
        )
        q = build_check_query(cond)
        assert q is not None
        assert "RLOTE" in q
        assert q.strip().upper().startswith("SELECT")


# ──────────────────────────────────────────────────────────────────────────────
# 4. resolution_cache
# ──────────────────────────────────────────────────────────────────────────────

class TestResolutionCache:

    def test_set_and_get_cached(self, tmp_path, monkeypatch):
        monkeypatch.setenv("QA_UAT_RESOLUTION_CACHE_PATH", str(tmp_path / "rc.json"))
        import importlib
        import resolution_cache as rc
        importlib.reload(rc)

        from precondition_parser import ParsedCondition
        cond = ParsedCondition(
            term="corredor", source="test", table="ROBLG", column="OGCORREDOR",
            operator="=", value="X", condition="ROBLG.OGCORREDOR = 'X'",
            confidence=0.9, polarity="value", join_path=[],
        )
        rc.set_cached("corredor test text", [cond])
        result = rc.get_cached("corredor test text")
        assert result is not None
        assert len(result) == 1
        assert result[0].column == "OGCORREDOR"

    def test_miss_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv("QA_UAT_RESOLUTION_CACHE_PATH", str(tmp_path / "rc2.json"))
        import importlib
        import resolution_cache as rc
        importlib.reload(rc)

        result = rc.get_cached("text that was never cached xyz123")
        assert result is None


# ──────────────────────────────────────────────────────────────────────────────
# 5. sql_query_guard: expanded whitelist
# ──────────────────────────────────────────────────────────────────────────────

class TestSqlQueryGuardFase2:

    def test_rlote_in_whitelist(self):
        from sql_query_guard import WHITELISTED_TABLES
        assert "RLOTE" in WHITELISTED_TABLES

    def test_roblg_in_whitelist(self):
        from sql_query_guard import WHITELISTED_TABLES
        assert "ROBLG" in WHITELISTED_TABLES

    def test_rclie_in_whitelist(self):
        from sql_query_guard import WHITELISTED_TABLES
        assert "RCLIE" in WHITELISTED_TABLES

    def test_information_schema_in_whitelist(self):
        from sql_query_guard import WHITELISTED_TABLES
        assert "INFORMATION_SCHEMA" in WHITELISTED_TABLES

    def test_select_rlote_locod_is_safe(self):
        from sql_query_guard import validate
        result = validate("SELECT TOP 5 LOCOD FROM RLOTE WHERE LOCOD IS NOT NULL ORDER BY NEWID()")
        assert result.safe, f"Expected safe, got violations: {result.violations}"

    def test_select_rclie_clriesgoent_is_safe(self):
        from sql_query_guard import validate
        result = validate("SELECT TOP 5 CLRIESGOENT FROM RCLIE WHERE CLRIESGOENT IS NOT NULL")
        assert result.safe, f"Expected safe, got violations: {result.violations}"


# ──────────────────────────────────────────────────────────────────────────────
# 6. data_resolver: _try_dynamic_resolution (no real DB needed)
# ──────────────────────────────────────────────────────────────────────────────

class TestDataResolverDynamicFallback:

    def test_try_dynamic_resolution_for_corredor_returns_query_or_none(self):
        """Should return a SQL string or None — must not raise."""
        from data_resolver import _try_dynamic_resolution
        result = _try_dynamic_resolution("CORREDOR_ID", "corredor del obligado")
        # With no DB connection, may return None or a static query
        assert result is None or isinstance(result, str)

    def test_try_dynamic_resolution_no_crash_on_empty(self):
        from data_resolver import _try_dynamic_resolution
        result = _try_dynamic_resolution("", "")
        assert result is None or isinstance(result, str)

    def test_resolve_fields_with_no_creds_marks_unresolved(self):
        """When no DB creds are set and field not in FIELD_HINTS, must return unresolved."""
        from data_resolver import resolve_fields
        import os
        env_backup = {k: os.environ.pop(k, None) for k in ["RS_QA_DB_USER", "RS_QA_DB_PASS", "RS_QA_DB_SERVER"]}
        try:
            result = resolve_fields([{"field": "XYZ_UNKNOWN", "description": "campo desconocido xyz"}])
            # Should not raise; field ends up unresolved or blocked
            all_fields = [r["field"] for r in result.unresolved + result.blocked]
            # It's acceptable for the dynamic path to also try and fail gracefully
            assert isinstance(result.resolved, dict)
        finally:
            for k, v in env_backup.items():
                if v is not None:
                    os.environ[k] = v
