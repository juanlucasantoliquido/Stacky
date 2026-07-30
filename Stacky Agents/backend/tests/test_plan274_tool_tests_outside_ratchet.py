"""
test_plan274_tool_tests_outside_ratchet.py — Plan 274 F0.3.

Documenta el HECHO DE HOY (hallazgo H8): los ~90 archivos de test del QA UAT
Agent viven en `Stacky tools/QA UAT Agent/tests/` y NO estan en ninguno de los
dos ratchets del arnes, asi que no tienen gate automatico.

F8.3 decidio, con evidencia, que esta deuda se ACEPTA en lugar de resolverse
(hallazgo V11). Tres motivos independientes:

  1. `run_harness_tests.sh` hace `cd backend` y lista rutas PELADAS, sin
     comillas, dentro de un array bash. La ruta del tool tiene DOS espacios
     (`Stacky tools`, `QA UAT Agent`) => word-splitting: pytest recibiria
     `../../Stacky` y reventaria.
  2. Los dos meta-tests solo reconocen rutas bajo `tests/`:
     `_SH_RE  = ^\\s*(tests/[\\w/]+\\.py)\\s*$`
     `_PS1_RE = ^\\s*"(tests/[\\w/]+\\.py)"\\s*,?\\s*$`
     (`tests/test_plan259_ratchet_script_parity.py:27,29`). `[\\w/]` no admite
     espacios ni puntos => una entrada del tool quedaria registrada MUDA:
     presente en el script y vigilada por ningun gate. Falso verde de manual.
  3. `test_plan259_ratchet_script_parity.py` compara los dos scripts como
     CONJUNTOS y ya divergen en 64 entradas (718 vs 654), asi que cualquier
     registro asimetrico agrava un rojo ajeno.

Por eso este test NO se invierte en F8.3: describe una deuda declarada, no un
objetivo pendiente. Lo unico obligatorio fue registrar los 2 archivos de test
de BACKEND del plan 274 en los dos scripts.
"""
from __future__ import annotations

import pathlib

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_SH = _BACKEND / "scripts" / "run_harness_tests.sh"
_PS1 = _BACKEND / "scripts" / "run_harness_tests.ps1"

_MENSAJE = (
    "H8: los ~90 tests del tool no tienen gate automatico; F8 decide si entran "
    "al ratchet o se declara deuda aceptada. En v3 se declaro ACEPTADA con los "
    "3 motivos del docstring de este archivo (hallazgo V11). Si este test falla "
    "es porque alguien metio el tool al ratchet: verificar que las rutas con "
    "espacios no queden MUDAS frente a _SH_RE / _PS1_RE antes de celebrar."
)


def test_los_tests_del_tool_no_estan_en_el_ratchet():
    for script in (_SH, _PS1):
        assert script.is_file(), f"falta el script del ratchet: {script}"
        hits = [
            f"{script.name}:{i + 1}"
            for i, line in enumerate(script.read_text(encoding="utf-8", errors="replace").splitlines())
            if "QA UAT Agent" in line
        ]
        assert not hits, f"{_MENSAJE}\nMenciones encontradas: {hits}"
