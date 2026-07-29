"""Plan 269 F7 — Alta completa de las 5 flags y registro en los DOS arneses.

Sin este archivo, `test_default_known_only_for_curated` y el meta-test de
registro quedan rojos y el plan "funciona" con el arnes roto.

9 casos, el ultimo es el que hace que los centinelas del DoD se auto-testeen.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS  # noqa: E402

LAS_5 = (
    "STACKY_RUN_VERDICT_ENABLED",
    "STACKY_RUN_EVIDENCE_COLLECTORS_ENABLED",
    "STACKY_UI_RUN_VERDICT_BADGE_ENABLED",
    "STACKY_INCIDENT_INBOX_VERDICT_ENABLED",
    "STACKY_RUN_RECONCILIATION_HITL_ENABLED",
)

LOS_6_TESTS = (
    "tests/test_plan269_run_verdict.py",
    "tests/test_plan269_run_evidence.py",
    "tests/test_plan269_executions_payload.py",
    "tests/test_plan269_inbox_verdict.py",
    "tests/test_plan269_hitl_correccion.py",
    "tests/test_plan269_flags.py",
)

SCRIPTS = ROOT / "scripts"


def _spec(key):
    return next((s for s in FLAG_REGISTRY if s.key == key), None)


def test_1_las_5_flags_estan_en_el_registro():
    for k in LAS_5:
        assert _spec(k) is not None, f"{k} no esta en FLAG_REGISTRY"


def test_2_las_5_son_default_true():
    for k in LAS_5:
        spec = _spec(k)
        assert spec is not None
        assert spec.default is True, f"{k} tiene default {spec.default!r}, se esperaba True"
        assert spec.type == "bool"


def test_3_las_5_estan_categorizadas():
    aplanado = {k for keys in _CATEGORY_KEYS.values() for k in keys}
    for k in LAS_5:
        assert k in aplanado, f"{k} no esta en ninguna categoria de _CATEGORY_KEYS"


def test_4_las_5_tienen_plain_help():
    from services.harness_flags_help import PLAIN_HELP

    for k in LAS_5:
        assert k in PLAIN_HELP, f"{k} no tiene ayuda llana"
        e = PLAIN_HELP[k]
        # Los 5 topes duros del contrato de PlainHelp.
        assert 10 <= len(e.what.strip()) <= 200, f"{k}: what fuera de rango"
        assert len(e.on_effect) <= 240, f"{k}: on_effect > 240"
        assert len(e.off_effect) <= 240, f"{k}: off_effect > 240"
        assert len(e.example) <= 300, f"{k}: example > 300"
        assert e.on_effect.startswith("Si "), f"{k}: on_effect no empieza con 'Si '"
        assert e.off_effect.startswith("Si "), f"{k}: off_effect no empieza con 'Si '"


def test_5_las_5_estan_curadas():
    from tests.test_harness_flags import _CURATED_DEFAULTS_ON

    for k in LAS_5:
        assert k in _CURATED_DEFAULTS_ON, f"{k} falta en _CURATED_DEFAULTS_ON"


def test_6_las_5_estan_en_config():
    from config import config as cfg

    for k in LAS_5:
        assert hasattr(cfg, k), f"{k} no existe en la instancia de Config"
        assert getattr(cfg, k) is True, f"{k} no vale True de fabrica"


def test_7_ninguna_declara_requires():
    """Asi no hay que tocar _REQUIRES_MAP_FROZEN, cuyo test compara por igualdad."""
    for k in LAS_5:
        spec = _spec(k)
        assert not getattr(spec, "requires", None), f"{k} declara requires"


def test_8_los_6_tests_estan_en_los_dos_scripts():
    sh = (SCRIPTS / "run_harness_tests.sh").read_text(encoding="utf-8", errors="replace")
    ps1 = (SCRIPTS / "run_harness_tests.ps1").read_text(encoding="utf-8", errors="replace")
    faltan = []
    for ruta in LOS_6_TESTS:
        nombre = ruta.split("/")[-1]
        if nombre not in sh:
            faltan.append((nombre, "sh"))
        if nombre not in ps1:
            faltan.append((nombre, "ps1"))
    assert faltan == [], (
        "faltan en el arnes: "
        + ", ".join(f"{n} -> {cual}" for n, cual in faltan)
        + ". El meta-test solo parsea el .sh, asi que el .ps1 se desincroniza en "
          "silencio: hay que agregarlo a los DOS."
    )


# (regex del centinela del DoD, sondas POSITIVAS, sondas NEGATIVAS)
_CENTINELAS = [
    (
        # El anti-patron que colapsa run y ticket, en sus 3 ortografias.
        r'stacky_status"? *,? *(None)?\)? *or *[a-z_]+\.status',
        [
            'estado = (getattr(ticket, "stacky_status", None) or ex.status or "")',
            'estado = getattr(by_tid.get(tid),"stacky_status",None) or ex.status or ""',
            'estado = ticket.stacky_status or ex.status or ""',
        ],
        [
            'run_status=(ex.status or ""),',
            'ticket_status=getattr(ticket, "stacky_status", None),',
        ],
    ),
    (
        # El chip del veredicto. El simbolo REAL es verdictChipTone.
        r"verdictChipTone",
        ["  const t = verdictChipTone(v.tone);"],
        ["  const t = runStatusTone(item.status);"],
    ),
    (
        # El endpoint PERMITIDO, sin arrastrar el que publica en el tracker.
        r"def set_stacky_status\(",
        ["def set_stacky_status(ticket_id: int):"],
        ["def set_stacky_status_by_ado(ado_id: int):"],
    ),
]


def test_9_los_centinelas_del_dod_si_pueden_disparar():
    """Cada gate de grep del DoD se prueba en LAS DOS direcciones.

    Un centinela que no matchea el pecado que prohibe es confianza falsa. Este
    plan ya tuvo tres gates que no podian disparar: uno grepeaba un simbolo que
    no era substring del real, otro tenia espacios que la variante real no tiene,
    y un tercero era prefijo de un simbolo distinto (y el equivocado publica en el
    tracker del operador). Este test lo hace imposible.
    """
    for patron, deben, no_deben in _CENTINELAS:
        rx = re.compile(patron)
        for s in deben:
            assert rx.search(s), f"centinela {patron!r} NO atrapa el pecado: {s!r}"
        for s in no_deben:
            assert not rx.search(s), f"centinela {patron!r} da FALSO POSITIVO en: {s!r}"
