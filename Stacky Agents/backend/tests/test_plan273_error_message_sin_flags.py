"""Plan 273 F5 (B-06) + F9 — ningun cuerpo de error de la API nombra una variable
de entorno STACKY_* en el texto que ve el operador.

DISENO DEL GATE, y es deliberado: se corre SOBRE EL FUENTE de backend/api/*.py, no
levantando la app y recorriendo endpoints. Recorrer endpoints requiere
create_app(), que fuera de pytest tiene efectos reales (arranca daemons, escribe
en la DB viva) y en pytest necesitaria 24 combinaciones de flags apagadas:
costoso, fragil y con contaminacion conocida. Sobre el fuente el gate es
determinista y corre igual en los 3 runtimes, en Windows y fuera.

COSTO DECLARADO: no detecta un `message` construido dinamicamente por f-string con
el nombre de la flag. Se tapa con `test_ningun_message_se_arma_por_fstring_con_la_flag`.
"""
from __future__ import annotations

import json
import pathlib
import re

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_API = _BACKEND / "api"
_FINGERPRINTS = _BACKEND.parent / "docs" / "sistema" / "error_fingerprints.json"

# Las claves que el operador LEE. `detail.flag` queda fuera a proposito: ahi el
# nombre de la flag SI corresponde (habilita el deep-link a Configuracion -> Flags).
_MESSAGE_RE = re.compile(r'"message":\s*"[^"]*STACKY_[A-Z0-9_]+')
_ERROR_RE = re.compile(r'"error":\s*"[^"]*STACKY_[A-Z0-9_]+')
_FLAG_IN_DETAIL_RE = re.compile(r'"flag":\s*"STACKY_[A-Z0-9_]+')

#: Los 13 archivos con cadenas de B-06, medidos el 2026-07-30 con
#: grep -rlE '"(error|message)":\s*"[^"]*STACKY_[A-Z_]+' backend/api --include=*.py
_LOS_13 = (
    "db_compare.py",
    "db_compare_demo.py",
    "db_compare_masking.py",
    "db_compare_repo.py",
    "db_compare_watch.py",
    "diag.py",
    "docs.py",
    "evolution.py",
    "evolution_fitness.py",
    "evolution_knowledge.py",
    "evolution_optimizer.py",
    "migrator.py",
    "plans_board.py",
)


def _api_files() -> list[pathlib.Path]:
    return sorted(_API.glob("*.py"))


def _hits(rx: re.Pattern[str]) -> list[str]:
    """Devuelve `archivo:linea: fragmento` de cada coincidencia.

    Se afirma sobre la LISTA, no sobre un contador: `assert count == 0` colapsa 24
    en "1 != 0" y el implementador arregla una, corre, sigue rojo y no sabe cuantas
    quedan. El mensaje TIENE que enumerar.
    """
    out: list[str] = []
    for p in _api_files():
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            m = rx.search(line)
            if m:
                out.append(f"api/{p.name}:{i}: {m.group(0)[:90]}")
    return out


def test_el_censo_no_es_vacio():
    """Un glob roto daria 0 archivos y todos los demas casos pasarian EN FALSO."""
    files = _api_files()
    assert len(files) >= 30, f"solo {len(files)} archivos en backend/api/"


def test_ningun_message_nombra_una_flag():
    hits = _hits(_MESSAGE_RE)
    assert hits == [], (
        f"{len(hits)} cuerpo(s) de error nombran una variable de entorno en la clave "
        f"`message`, que es texto para el operador:\n" + "\n".join(hits)
    )


def test_ningun_error_nombra_una_flag():
    hits = _hits(_ERROR_RE)
    assert hits == [], (
        f"{len(hits)} cuerpo(s) de error nombran una variable de entorno en la clave "
        f"`error`:\n" + "\n".join(hits)
    )


def test_ningun_message_se_arma_por_fstring_con_la_flag():
    """Tapa el hueco declarado del gate: un message armado dinamicamente."""
    hits: list[str] = []
    for p in _api_files():
        for i, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if '"message"' not in line:
                continue
            if re.search(r'f"[^"]*STACKY_|f\'[^\']*STACKY_', line):
                hits.append(f"api/{p.name}:{i}: {line.strip()[:90]}")
    assert hits == [], "message armado por f-string con el nombre de la flag:\n" + "\n".join(hits)


def test_los_13_archivos_declaran_detail_flag():
    """El nombre de la flag no se PERDIO: se movio a detail.flag, donde sirve."""
    missing = [
        name for name in _LOS_13
        if not _FLAG_IN_DETAIL_RE.search((_API / name).read_text(encoding="utf-8", errors="replace"))
    ]
    assert missing == [], (
        "estos archivos no declaran ningun `detail: {\"flag\": \"STACKY_...\"}`, asi que "
        "el nombre de la flag se perdio en vez de moverse:\n" + "\n".join(missing)
    )


def test_el_conteo_de_detail_flag_cubre_las_24():
    """Prueba que se migraron TODAS, no algunas."""
    total = sum(
        len(_FLAG_IN_DETAIL_RE.findall((_API / n).read_text(encoding="utf-8", errors="replace")))
        for n in _LOS_13
    )
    assert total >= 24, (
        f"solo {total} ocurrencias de `\"flag\": \"STACKY_...\"` en los 13 archivos; "
        f"se esperaban >= 24 (una por cada cuerpo reescrito)"
    )


# ── F9 — huella de regresion ──────────────────────────────────────────────────
def test_la_huella_de_regresion_esta_registrada():
    """Auto-referencial a proposito: si alguien borra este archivo de test, la
    huella queda apuntando a un archivo inexistente y este caso lo grita."""
    data = json.loads(_FINGERPRINTS.read_text(encoding="utf-8"))
    entries = data["fingerprints"]
    match = [e for e in entries if e.get("id") == "error_body_nombra_flag_de_entorno"]
    assert match, (
        "falta la huella `error_body_nombra_flag_de_entorno` en "
        "docs/sistema/error_fingerprints.json"
    )
    fp = match[0]
    assert fp["status"] == "resolved", f"status={fp['status']!r}"
    guard = fp["guard_test"]
    assert guard == "tests/test_plan273_error_message_sin_flags.py", (
        f"guard_test apunta a {guard!r}, no a este archivo"
    )
    assert (_BACKEND / guard).exists(), f"el guard_test {guard} no existe en el disco"
    # C24: `self_test` es obligatorio (test_error_fingerprints_catalog.py:18) y sus
    # muestras se verifican contra el log_pattern. Se comprueba ACA porque el gate
    # compartido muere antes con un KeyError en una huella ajena del plan 239.
    assert "self_test" in fp, "la huella no declara self_test (lo exige el catalogo)"
    pat = re.compile(fp["log_pattern"])
    for sample in fp["self_test"]["matches"]:
        assert pat.search(sample), f"self_test.matches no matchea el log_pattern: {sample!r}"
    for sample in fp["self_test"]["clean"]:
        assert not pat.search(sample), f"self_test.clean SI matchea el log_pattern: {sample!r}"
