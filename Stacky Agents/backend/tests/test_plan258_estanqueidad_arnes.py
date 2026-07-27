"""Plan 258 F7 — guard de estanqueidad del arnes.

EL INVARIANTE, uno solo: *una corrida del arnes no debe modificar ningun
artefacto de runtime del operador.* Un enunciado verificable que cubre los
archivos presentes Y los futuros.

Por que hace falta: todo el resto del plan persigue la contaminacion archivo por
archivo y marcador por marcador (`env_applies.jsonl` por el root de pytest,
`ci_runs.jsonl` por `myproject`, el log por 'DB exploded'). Eso es artesanal y no
escala: `build_runs.jsonl` aparecio y estuvo desprotegido sin que nadie lo
notara. Un glob los cubre a todos.

Correr POR ARCHIVO:
    .venv\\Scripts\\python.exe -m pytest tests/test_plan258_estanqueidad_arnes.py -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "airtight_snapshot.py"


@pytest.fixture
def raiz(tmp_path):
    """Arbol falso con la misma forma que backend/: data/ con un .jsonl, un log
    y una base."""
    (tmp_path / "data" / "logs").mkdir(parents=True)
    (tmp_path / "data" / "db_compare").mkdir(parents=True)
    (tmp_path / "data" / "ci_runs.jsonl").write_text('{"a": 1}\n', encoding="utf-8")
    (tmp_path / "data" / "db_compare" / "sql_exec_ledger.jsonl").write_text(
        '{"b": 2}\n', encoding="utf-8")
    (tmp_path / "data" / "logs" / "stacky-2026-01-01.log").write_text("hola\n", encoding="utf-8")
    (tmp_path / "data" / "stacky_agents.db").write_bytes(b"SQLite format 3\x00")
    return tmp_path


def _snap(raiz):
    from scripts.airtight_snapshot import snapshot
    return snapshot(raiz)


# ---------------------------------------------------------------------------
# Nucleo: snapshot + diff
# ---------------------------------------------------------------------------

def test_snapshot_detecta_modificacion(raiz):
    from scripts.airtight_snapshot import diff_snapshots

    antes = _snap(raiz)
    with (raiz / "data" / "ci_runs.jsonl").open("a", encoding="utf-8") as fh:
        fh.write('{"a": 2}\n')
    cambios = diff_snapshots(antes, _snap(raiz))

    assert len(cambios) == 1
    assert "MODIFICADO" in cambios[0]
    assert "data/ci_runs.jsonl" in cambios[0]
    assert "+10 bytes" in cambios[0]          # '{"a": 2}\n' = 9 chars + salto = 10
    assert "10 -> 20" in cambios[0]


def test_snapshot_detecta_archivo_nuevo(raiz):
    """Caso exacto de `ado_edit_learned.jsonl`, que hoy NO existe: si una corrida
    lo crea, eso tambien es una violacion."""
    from scripts.airtight_snapshot import diff_snapshots

    antes = _snap(raiz)
    (raiz / "data" / "ado_edit_learned.jsonl").write_text('{"nuevo": true}\n', encoding="utf-8")
    cambios = diff_snapshots(antes, _snap(raiz))

    assert len(cambios) == 1
    assert cambios[0].startswith("CREADO")
    assert "data/ado_edit_learned.jsonl" in cambios[0]


def test_snapshot_detecta_borrado(raiz):
    from scripts.airtight_snapshot import diff_snapshots

    antes = _snap(raiz)
    (raiz / "data" / "ci_runs.jsonl").unlink()
    cambios = diff_snapshots(antes, _snap(raiz))

    assert len(cambios) == 1
    assert cambios[0].startswith("BORRADO")
    assert "data/ci_runs.jsonl" in cambios[0]


def test_snapshot_vacio_si_nada_cambia(raiz):
    """CONTROL NEGATIVO. Sin este caso el guard podria estar siempre verde
    (p. ej. si `snapshot` devolviera {} por un glob mal escrito) y nadie lo
    notaria hasta que dejara pasar una contaminacion real."""
    from scripts.airtight_snapshot import diff_snapshots

    antes = _snap(raiz)
    assert len(antes) == 4, f"el glob no esta viendo los 4 artefactos: {sorted(antes)}"
    assert sorted(antes) == [
        "data/ci_runs.jsonl",
        "data/db_compare/sql_exec_ledger.jsonl",
        "data/logs/stacky-2026-01-01.log",
        "data/stacky_agents.db",
    ]
    assert diff_snapshots(antes, _snap(raiz)) == []

    # Leer NO es modificar: el guard no debe disparar por un acceso de lectura.
    (raiz / "data" / "ci_runs.jsonl").read_text(encoding="utf-8")
    assert diff_snapshots(antes, _snap(raiz)) == []


def test_verify_sale_con_codigo_1_y_nombra_el_archivo(raiz, tmp_path):
    """Criterio binario del guard, ejercitado por la CLI de verdad."""
    huella = tmp_path / "huella.json"
    base = [sys.executable, str(SCRIPT), "--root", str(raiz), "--snapshot-file", str(huella)]

    guardado = subprocess.run(base + ["--save"], capture_output=True, text=True)
    assert guardado.returncode == 0, guardado.stderr
    assert huella.is_file()

    limpio = subprocess.run(base + ["--verify"], capture_output=True, text=True)
    assert limpio.returncode == 0, limpio.stderr

    with (raiz / "data" / "env_applies.jsonl").open("w", encoding="utf-8") as fh:
        fh.write('{"root": "C:/tmp/pytest-of-juanluca/x"}\n')

    sucio = subprocess.run(base + ["--verify"], capture_output=True, text=True)
    assert sucio.returncode == 1, f"stdout={sucio.stdout!r} stderr={sucio.stderr!r}"
    assert "env_applies.jsonl" in sucio.stderr
    assert "CREADO" in sucio.stderr


# ---------------------------------------------------------------------------
# Alcance y casos borde
# ---------------------------------------------------------------------------

def test_snapshot_sin_data_devuelve_vacio(tmp_path):
    """Checkout limpio sin `data/`: el guard pasa trivialmente, no explota."""
    from scripts.airtight_snapshot import diff_snapshots

    assert _snap(tmp_path) == {}
    assert diff_snapshots({}, {}) == []


def test_los_jsonl_no_se_excluyen_nunca(raiz, tmp_path):
    """El log del DIA en curso se excluye por default (el operador puede tener el
    servicio corriendo mientras testea). Un `.jsonl` NO se excluye jamas: un
    archivo de registro no debe crecer por una corrida de tests bajo ninguna
    circunstancia."""
    from datetime import date

    from scripts.airtight_snapshot import _filtrar, _log_del_dia

    hoy = _log_del_dia()
    assert hoy == f"data/logs/stacky-{date.today().isoformat()}.log"

    cambios = [
        f"MODIFICADO  {hoy} (+10 bytes, 0 -> 10)",
        "MODIFICADO  data/ci_runs.jsonl (+10 bytes, 0 -> 10)",
    ]
    quedan = _filtrar(cambios, (hoy,))
    assert len(quedan) == 1
    assert "ci_runs.jsonl" in quedan[0]


def test_watched_globs_cubre_los_artefactos_del_operador():
    from scripts.airtight_snapshot import WATCHED_GLOBS

    assert "data/*.jsonl" in WATCHED_GLOBS
    assert "data/**/*.jsonl" in WATCHED_GLOBS       # data/db_compare/sql_exec_ledger.jsonl
    assert "data/logs/*.log" in WATCHED_GLOBS
    assert "data/*.db" in WATCHED_GLOBS
    # La base corre en WAL (plan 253): el -wal es parte del dato, no un temporal.
    assert "data/*.db-wal" in WATCHED_GLOBS


def test_guard_apagado_no_verifica_nada(raiz, tmp_path, monkeypatch):
    """Con la perilla apagada el guard sale en 0 sin comparar. Se lee por entorno
    porque corre como script suelto, FUERA del proceso del servicio."""
    huella = tmp_path / "huella.json"
    base = [sys.executable, str(SCRIPT), "--root", str(raiz), "--snapshot-file", str(huella)]
    subprocess.run(base + ["--save"], capture_output=True, text=True, check=True)
    (raiz / "data" / "ci_runs.jsonl").write_text('{"cambiado": 1}\n', encoding="utf-8")

    entorno = {**os.environ, "STACKY_HARNESS_AIRTIGHT_GUARD_ENABLED": "false"}
    apagado = subprocess.run(base + ["--verify"], capture_output=True, text=True, env=entorno)
    assert apagado.returncode == 0

    prendido = subprocess.run(base + ["--verify"], capture_output=True, text=True)
    assert prendido.returncode == 1


def test_verify_sin_huella_previa_no_miente(tmp_path, raiz):
    """Sin huella previa NO se puede afirmar estanqueidad: sale distinto de 0 y
    lo dice. Un guard que devuelva 0 sin haber comparado nada es un falso verde."""
    huella = tmp_path / "no-existe.json"
    res = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(raiz),
         "--snapshot-file", str(huella), "--verify"],
        capture_output=True, text=True)
    assert res.returncode == 2
    assert "NO hay huella previa" in res.stderr


def test_snapshot_huella_cambia_con_el_contenido_no_solo_con_el_tamano(raiz):
    """El sha256 esta en la huella a proposito: una reescritura del MISMO tamano
    (exactamente lo que hace `tmp.replace` al purgar) tiene que verse."""
    from scripts.airtight_snapshot import diff_snapshots

    antes = _snap(raiz)
    (raiz / "data" / "ci_runs.jsonl").write_text('{"a": 9}\n', encoding="utf-8")
    despues = _snap(raiz)

    assert antes["data/ci_runs.jsonl"][0] == despues["data/ci_runs.jsonl"][0]  # mismo tamano
    assert antes["data/ci_runs.jsonl"][1] != despues["data/ci_runs.jsonl"][1]  # distinto sha
    assert len(diff_snapshots(antes, despues)) == 1


def test_snapshot_file_vive_fuera_del_arbol_vigilado():
    """La huella no puede ser su propio falso positivo."""
    import tempfile

    from scripts.airtight_snapshot import SNAPSHOT_FILE

    assert SNAPSHOT_FILE.parent == Path(tempfile.gettempdir())
    assert "data" not in SNAPSHOT_FILE.parts
    assert not str(SNAPSHOT_FILE).startswith(str(BACKEND))
