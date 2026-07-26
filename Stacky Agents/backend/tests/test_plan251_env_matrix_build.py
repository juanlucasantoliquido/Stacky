"""Plan 251 F2 — entornos DERIVADOS + construccion de la matriz. 13 tests. PURO."""
from __future__ import annotations

import json
from pathlib import Path

from services import pipeline_environments as pe

BACKEND = Path(__file__).resolve().parent.parent
GOLDEN = BACKEND / "tests" / "fixtures" / "cicd_nl" / "golden"
ADO = pe.PROVIDER_ADO
GL = pe.PROVIDER_GITLAB


def _leer(nombre: str) -> str:
    return (GOLDEN / nombre).read_text(encoding="utf-8")


def _req(name, kind="variable", **kw):
    base = dict(provider=ADO, is_secret=False, declared_default=None,
                per_environment=True, confidence="alta", evidence=())
    base.update(kw)
    return pe.Requirement(name=name, kind=kind, **base)


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_f2_bootstrap_deriva_test_y_production():
    assert pe.derive_environments(
        _leer("bootstrap-server-environment.yml"), ADO) == ("Test", "Production")


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_f2_cd_deploy_deriva_solo_test():
    assert pe.derive_environments(_leer("cd-deploy-test.yml"), ADO) == ("Test",)


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_f2_sin_evidencia_una_sola_columna():
    """KPI-4 — NUNCA se fabrica Dev/QA/Prod."""
    assert pe.derive_environments(_leer("nightly-build-online.yml"), ADO) == (pe.ENV_UNICO,)


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_f2_orden_canonico():
    assert pe.derive_environments("a: 1\n", ADO,
                                  ("prod", "dev", "staging", "zeta")) == (
        "dev", "staging", "prod", "zeta")


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_f2_dedup_case_insensitive():
    assert pe.derive_environments("a: 1\n", ADO, ("Test", "test", "TEST")) == ("Test",)


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_f2_matriz_cubre_todas_las_celdas():
    reqs = tuple(_req("V%d" % i) for i in range(5))
    m = pe.build_matrix(reqs, ("Test", "Production"), {}, ADO)
    assert len(m.cells) == 5 * 2


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_f2_pending_count_cuenta_solo_falta():
    reqs = (_req("A"), _req("B"), _req("C"),
            _req("MiSub", kind="service_connection"), _req("D"))
    resol = {("A", "Test"): ("definido", "caja_fuerte", None),
             ("B", "Test"): ("definido", "yaml_variables", None)}
    m = pe.build_matrix(reqs, ("Test",), resol, ADO)
    assert m.pending_count == 2       # C y D; MiSub cae a `manual`
    estados = {c.requirement: c.state for c in m.cells}
    assert estados["MiSub"] == "manual"


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_f2_nota_ado_sin_scoping():
    m = pe.build_matrix((_req("A"),), ("Test", "Production"),
                        {("A", "Test"): ("definido", "caja_fuerte", None),
                         ("A", "Production"): ("definido", "caja_fuerte", None)}, ADO)
    for c in m.cells:
        assert c.note and "definition" in c.note


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_f2_gitlab_sin_nota_de_ado():
    m = pe.build_matrix((_req("A", provider=GL),), ("Test", "Production"),
                        {("A", "Test"): ("definido", "caja_fuerte", None),
                         ("A", "Production"): ("definido", "caja_fuerte", None)}, GL)
    for c in m.cells:
        assert not (c.note and "definition" in c.note)


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_f2_build_matrix_es_pura():
    reqs = (_req("A"), _req("B"))
    resol = {("A", "Test"): ("definido", "caja_fuerte", None)}
    copia_reqs, copia_resol = tuple(reqs), dict(resol)
    m1 = pe.build_matrix(reqs, ("Test",), resol, ADO)
    m2 = pe.build_matrix(reqs, ("Test",), resol, ADO)
    assert m1 == m2
    assert reqs == copia_reqs and resol == copia_resol


# ── 11 ───────────────────────────────────────────────────────────────────────
def test_f2_payload_serializa_sin_error():
    """C3 — con el dict de claves TUPLA de la v1 esto era un TypeError."""
    texto = _leer("bootstrap-server-environment.yml")
    reqs = pe.extract_requirements(texto, ADO)
    m = pe.build_matrix(reqs, pe.derive_environments(texto, ADO), {}, ADO)
    payload = pe.to_json_payload(m, ADO)
    crudo = json.dumps(payload)
    assert isinstance(payload["cells"], list)
    for celda in payload["cells"]:
        assert set(celda) == {"requirement", "environment", "state", "source", "note"}
    assert "\x00" not in crudo


# ── 12 ───────────────────────────────────────────────────────────────────────
def test_f2_pending_fingerprint_estable():
    reqs = (_req("A"), _req("B"), _req("C"))
    m1 = pe.build_matrix(reqs, ("Test", "Production"), {}, ADO)
    m2 = pe.build_matrix(reqs, ("Test", "Production"), {}, ADO)
    assert m1.pending_fingerprint == m2.pending_fingerprint

    m3 = pe.build_matrix(reqs, ("Test", "Production"),
                         {("A", "Test"): ("definido", "caja_fuerte", None)}, ADO)
    assert m3.pending_fingerprint != m1.pending_fingerprint

    m4 = pe.build_matrix(reqs, ("Production", "Test"), {}, ADO)
    assert m4.pending_fingerprint == m1.pending_fingerprint, \
        "es sobre el CONJUNTO ordenado, no sobre el orden de llegada"


# ── 13 ───────────────────────────────────────────────────────────────────────
def test_f2_per_environment_false_lleva_nota():
    """C16 — `per_environment` deja de ser un campo muerto."""
    m = pe.build_matrix((_req("A", per_environment=False),), ("Test", "Production"),
                        {}, ADO)
    for c in m.cells:
        assert c.note and "todos los entornos" in c.note


def test_f2_confianza_baja_nunca_termina_en_falta():
    reqs = (_req("C:\\AIS\\X", kind="deploy_path", confidence="baja"),
            _req("dudosa", confidence="baja"))
    m = pe.build_matrix(reqs, ("Test",), {}, ADO)
    assert {c.state for c in m.cells} == {"manual"}
    assert m.pending_count == 0
