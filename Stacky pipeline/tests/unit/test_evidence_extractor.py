"""Tests T7 Evidence Extractor — Fase 2 / P2.5."""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from linters.evidence_extractor import extract_evidence, EvidenceBundle


def make_diff(file_path: str, added: list[str]) -> str:
    cb = " public class C {"
    return (
        f"diff --git a/{file_path} b/{file_path}\n"
        f"--- a/{file_path}\n"
        f"+++ b/{file_path}\n"
        f"@@ -1,1 +1,{1 + len(added)} @@\n"
        f"{cb}\n"
        + "\n".join("+" + l for l in added) + "\n"
    )


class TestEvidenceBasica:
    def test_diff_vacio_bundle_vacio(self):
        b = extract_evidence("")
        assert b.total() == 0

    def test_violacion_r2_marca_fail(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSBus/Foo.cs",
            ["    cConexion conn = new cConexion();"],
        )
        b = extract_evidence(diff)
        assert "R2" in b.by_rule
        assert b.by_rule["R2"][0].status == "FAIL"

    def test_uso_correcto_r2_marca_pass(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSFac/Foo.cs",
            ["    cConexion conn = new cConexion();"],
        )
        b = extract_evidence(diff)
        assert "R2" in b.by_rule
        assert b.by_rule["R2"][0].status == "PASS"

    def test_r1_pass_con_idm_texto(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSBus/Foo.cs",
            ['    Error.Agregar(Const.E, Idm.Texto(coMens.m1234, "fb"), "v", Const.S);'],
        )
        b = extract_evidence(diff)
        assert "R1" in b.by_rule
        assert b.by_rule["R1"][0].status == "PASS"

    def test_r1_fail_sin_idm_texto(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSBus/Foo.cs",
            ['    Error.Agregar(Const.E, "Mensaje hardcodeado", "v", Const.S);'],
        )
        b = extract_evidence(diff)
        assert "R1" in b.by_rule
        assert b.by_rule["R1"][0].status == "FAIL"

    def test_r4_pass_con_parametros(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSDalc/Foo.cs",
            ['    string sql = "SELECT * FROM RCLIE WHERE CLCOD = @p_cod";'],
        )
        b = extract_evidence(diff)
        assert "R4" in b.by_rule
        assert any(i.status == "PASS" for i in b.by_rule["R4"])

    def test_r4_fail_concat(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSDalc/Foo.cs",
            ['    string sql = "SELECT * FROM RCLIE WHERE CLCOD = \'" + var + "\'";'],
        )
        b = extract_evidence(diff)
        assert "R4" in b.by_rule
        assert any(i.status == "FAIL" for i in b.by_rule["R4"])


class TestMultiEmpresa:
    def test_query_rcle_con_clempresa_pass(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSDalc/Cliente.cs",
            ['    string sql = "SELECT * FROM RCLIE WHERE CLCOD = @p_cod AND CLEMPRESA = @p_emp";'],
        )
        b = extract_evidence(diff)
        assert "multi_empresa" in b.by_rule
        item = b.by_rule["multi_empresa"][0]
        assert item.status == "PASS"
        assert "RCLIE" in item.note

    def test_query_roblg_sin_filtro_review(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSDalc/Obligacion.cs",
            ['    string sql = "SELECT * FROM ROBLG WHERE OGCOD = @p_cod";'],
        )
        b = extract_evidence(diff)
        assert "multi_empresa" in b.by_rule
        item = b.by_rule["multi_empresa"][0]
        assert item.status == "REVIEW"


class TestBundleSerialization:
    def test_to_dict_es_json_serializable(self):
        import json
        diff = make_diff(
            "trunk/OnLine/Negocio/RSBus/Foo.cs",
            ["    cConexion conn = new cConexion();"],
        )
        b = extract_evidence(diff)
        d = b.to_dict()
        # Debe poder serializarse sin errores
        s = json.dumps(d)
        assert "R2" in s
        assert "FAIL" in s

    def test_fail_count(self):
        diff = make_diff(
            "trunk/OnLine/Negocio/RSBus/Foo.cs",
            [
                "    cConexion conn = new cConexion();",   # R2 FAIL
                "    conn.ComienzoTransaccion();",         # R3 FAIL
            ],
        )
        b = extract_evidence(diff)
        assert b.fail_count() >= 2
