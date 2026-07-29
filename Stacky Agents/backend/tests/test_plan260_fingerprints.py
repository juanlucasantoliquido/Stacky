"""Plan 260 F7 — huella de regresión.

Los dos falsos verdes que este plan corrige (declarar apaga la alerta; un
gate de secretos declarado contra un motor que no produce sus códigos) quedan
registrados en docs/sistema/error_fingerprints.json, para que el próximo que
los reintroduzca los vea nombrados.

(v5, C6) El test NO asertá longitud total exacta: otros planes hermanos
(259/267/270 ya, y varios más en cola) tocan el mismo archivo con el mismo
patrón F7; un total exacto quedaría rojo por una razón ajena la primera vez
que cualquiera de ellos merge después de este plan.
"""
from __future__ import annotations

import json
from pathlib import Path

DOCS_ROOT = Path(__file__).resolve().parents[2] / "docs" / "sistema" / "error_fingerprints.json"
CORPUS_DIR = Path(__file__).resolve().parent / "plan260_corpus"

_IDS_NUEVOS = {"declarar_apaga_la_alerta", "gate_de_secretos_inerte"}

# (v3, C10) El schema REAL del archivo — estas son las 12 claves que usa la
# GRAN MAYORIA de las huellas existentes (medido: 16/45 exactas, más otras
# variantes que agregan "self_test" u omiten "note"/"killed_commit" — el
# schema NO es 100% uniforme). Comparar contra una entrada "vecina" por
# posición (ej. fingerprints[-3]) es FRÁGIL: medido hoy, la 3ª desde el final
# tiene solo 10 claves (sin date_resolved/evidence/killed_commit) por una F7
# ajena. Por eso el set de referencia es el vocabulario CANÓNICO del plan,
# no una entrada vecina cuya forma puede haber driftado en horas.
_CAMPOS_CANONICOS = {
    "id", "title", "class", "status", "log_pattern", "log_guarded",
    "killed_by", "killed_commit", "date_resolved", "guard_test", "evidence", "note",
}


def _cargar() -> dict:
    return json.loads(DOCS_ROOT.read_text(encoding="utf-8"))


def _cargar_baseline() -> list:
    return json.loads((CORPUS_DIR / "fingerprints_baseline.json").read_text(encoding="utf-8"))


def test_f7_json_valido_y_solo_crecio():
    actual = _cargar()["fingerprints"]
    base = _cargar_baseline()
    assert actual[:len(base)] == base, (
        "una huella preexistente cambió o se borró (no es aditivo)")
    ids_presentes = {h["id"] for h in actual}
    assert _IDS_NUEVOS <= ids_presentes, "faltan las huellas nuevas de este plan"
    # A propósito NO se asserta len(actual) == len(base) + 2: otros planes
    # hermanos con fase F7 tocan el mismo archivo con el mismo patrón.


def test_f7_las_huellas_nuevas_usan_el_schema_existente():
    actual = _cargar()["fingerprints"]
    nuevas = [h for h in actual if h["id"] in _IDS_NUEVOS]
    assert len(nuevas) == 2
    for h in nuevas:
        claves = set(h.keys())
        assert claves == _CAMPOS_CANONICOS, (
            f"{h['id']}: claves {claves - _CAMPOS_CANONICOS} inventadas o "
            f"{_CAMPOS_CANONICOS - claves} faltantes"
        )


def test_f7_guard_test_apunta_a_un_archivo_que_existe():
    backend_root = Path(__file__).resolve().parents[1]  # backend/
    actual = _cargar()["fingerprints"]
    nuevas = [h for h in actual if h["id"] in _IDS_NUEVOS]
    for h in nuevas:
        ruta = backend_root / h["guard_test"]
        assert ruta.is_file(), f"{h['id']}: guard_test {h['guard_test']!r} no existe"
