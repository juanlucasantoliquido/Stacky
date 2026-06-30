"""Plan 49 F7 — anti-blindaje: los extractores DETECTAN, no solo existen.

Garantiza que el corpus contiene ambos polos de discriminación. Si un extractor
se neutraliza (siempre True / siempre False), o si el corpus pierde un polo,
estos meta-tests se vuelven rojos aunque cada fixture individual pase.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from evals.extraction_golden_runner import load_cases


def _epic_cases():
    return [
        c
        for c in load_cases()
        if c.kind == "epic" and "looks_like_epic" in c.expect
    ]


def test_looks_like_epic_discrimina_ambos_polos():
    polos = {c.expect["looks_like_epic"] for c in _epic_cases()}
    assert True in polos, "falta fixture epic con looks_like_epic=True"
    assert False in polos, "falta fixture epic con looks_like_epic=False (anti-narracion)"


def test_pending_task_cubre_json_roto_y_valido():
    pt = [
        c
        for c in load_cases()
        if c.kind == "pending_task" and "json_ok" in c.expect
    ]
    polos = {c.expect["json_ok"] for c in pt}
    assert True in polos and False in polos, (
        "el corpus pending_task debe cubrir JSON valido (true) y roto (false)"
    )
