# backend/tests/test_plan271_flags.py — el gate de la ayuda llana de ESTE plan.
# E3: NO se mide el conteo de test_harness_flags_help.py (que ya está rojo por 79
# faltantes ajenos y no cambia de color si omitís las tuyas). Se afirma pertenencia
# y se aplican los MISMOS cinco chequeos, acotados a las 4 keys del 271.
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

_PLAN271_KEYS = (
    "STACKY_FINAL_STATE_ROLE_FALLBACK_ENABLED",
    "STACKY_FINAL_STATE_WRITER_ROUTED_ENABLED",
    "STACKY_FINAL_STATE_PUBLISH_GATE_PRECISE_ENABLED",
    "STACKY_FINAL_STATE_REASON_VISIBLE_ENABLED",
)


def test_las_4_keys_tienen_ayuda_llana_y_pasan_los_cinco_chequeos():
    from services.harness_flags_help import PLAIN_HELP
    from tests.test_harness_flags_help import JARGON_DENYLIST, _KEY_RE, _PHASE_RE

    faltan = [k for k in _PLAN271_KEYS if k not in PLAIN_HELP]
    assert faltan == [], f"flags del 271 sin ayuda llana: {faltan}"

    for key in _PLAN271_KEYS:
        e = PLAIN_HELP[key]
        assert 10 <= len(e.what.strip()) and len(e.what) <= 200, f"{key}: what fuera de 10..200"
        for campo in ("on_effect", "off_effect"):
            v = getattr(e, campo)
            assert len(v) <= 240, f"{key}: {campo} > 240"
            assert v.startswith("Si "), f"{key}: {campo} no empieza con 'Si '"
        assert len(e.example) <= 300, f"{key}: example > 300"
        for campo in ("what", "on_effect", "off_effect", "example"):
            v = getattr(e, campo)
            assert v.strip(), f"{key}: {campo} vacío"
            for term in JARGON_DENYLIST:
                assert not re.search(rf"\b{re.escape(term)}s?\b", v, re.IGNORECASE), \
                    f"{key}.{campo}: jerga prohibida '{term}'"
            assert not _KEY_RE.search(v), f"{key}.{campo}: cita una key SCREAMING_SNAKE"
            assert not _PHASE_RE.search(v), f"{key}.{campo}: referencia a fase F<n>"


def test_las_4_keys_default_true_y_categoria_flujo_funcional():
    from services.harness_flags import FLAG_REGISTRY, _CATEGORY_KEYS

    by_key = {s.key: s for s in FLAG_REGISTRY}
    for key in _PLAN271_KEYS:
        assert key in by_key, f"{key} no está en FLAG_REGISTRY"
        assert by_key[key].default is True, f"{key}: default no es True"
        assert key in _CATEGORY_KEYS["flujo_funcional"], f"{key} no está en flujo_funcional"


def test_las_4_keys_no_declaran_requires():
    from services.harness_flags import FLAG_REGISTRY

    by_key = {s.key: s for s in FLAG_REGISTRY}
    for key in _PLAN271_KEYS:
        assert not getattr(by_key[key], "requires", None), \
            f"{key}: no debe declarar requires= (§3.1 pata 8)"


def test_las_4_keys_estan_en_harness_defaults_env():
    env_path = ROOT / "harness_defaults.env"
    content = env_path.read_text(encoding="utf-8")
    for key in _PLAN271_KEYS:
        assert f"{key}=true" in content, f"{key}=true no está en harness_defaults.env"


def test_discriminacion_del_gate_de_ayuda_llana():
    """Verificación de discriminación (§3.3bis, obligatoria): borrar una entrada
    de PLAIN_HELP tiene que poner ROJO este mismo test; reponerla, VERDE."""
    from services import harness_flags_help as hfh

    key = _PLAN271_KEYS[0]
    original = hfh.PLAIN_HELP[key]
    faltan_antes = [k for k in _PLAN271_KEYS if k not in hfh.PLAIN_HELP]
    assert faltan_antes == []

    del hfh.PLAIN_HELP[key]
    try:
        faltan_borrado = [k for k in _PLAN271_KEYS if k not in hfh.PLAIN_HELP]
        assert faltan_borrado == [key], "el gate no detectó la entrada borrada (no discrimina)"
    finally:
        hfh.PLAIN_HELP[key] = original

    faltan_repuesto = [k for k in _PLAN271_KEYS if k not in hfh.PLAIN_HELP]
    assert faltan_repuesto == []
