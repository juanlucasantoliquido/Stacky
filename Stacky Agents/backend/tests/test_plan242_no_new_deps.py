"""Plan 242 KPI-4 — ningun modulo nuevo importa numpy/sklearn/scipy/pandas.

Se verifica por AST y NO por regex: un regex sobre texto da falsos positivos
(un comentario o un string que diga 'numpy') y falsos negativos (un import
dentro de una funcion, indentado). El AST ve los imports REALES, esten donde
esten.

Alcance recortado (§0.3): los 3 modulos read-only de esta mitad. Los 4 que
escriben en disco (cost_model, cost_model_eval, cost_forecast_ledger,
cost_model_hooks) son del plan siguiente y NO existen todavia.
"""
import ast
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent

_PROHIBIDOS = {"numpy", "sklearn", "scipy", "pandas", "torch", "statsmodels"}
_RED = {"requests", "socket", "subprocess", "urllib", "http", "httpx"}

_MODULOS = (
    "services/cost_signals.py",
    "services/cost_stats.py",
    "services/cost_scoring.py",
)


def _imports_de(path: Path) -> set[str]:
    arbol = ast.parse(path.read_text(encoding="utf-8"))
    nombres = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for a in nodo.names:
                nombres.add(a.name.split(".")[0])
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.module:
                nombres.add(nodo.module.split(".")[0])
    return nombres


@pytest.mark.parametrize("rel", _MODULOS)
def test_ningun_modulo_nuevo_importa_dependencia_prohibida(rel):
    """KPI-4 — cero numpy, cero sklearn, cero scipy, cero pandas."""
    encontrados = _imports_de(BACKEND_ROOT / rel) & _PROHIBIDOS
    assert not encontrados, f"{rel} importa {sorted(encontrados)}"


@pytest.mark.parametrize("rel", _MODULOS)
def test_los_3_modulos_existen(rel):
    """Anti-falso-verde: un test que pasa porque el archivo no existe no prueba nada."""
    assert (BACKEND_ROOT / rel).is_file(), f"falta {rel}"


@pytest.mark.parametrize("rel", _MODULOS)
def test_ningun_modulo_nuevo_importa_requests_socket_subprocess(rel):
    """G3 — sin LLM, sin red, sin shell-out: todo es aritmetica local."""
    encontrados = _imports_de(BACKEND_ROOT / rel) & _RED
    assert not encontrados, f"{rel} importa {sorted(encontrados)}"


def test_cost_signals_no_importa_cost_analytics():
    """F0.1 anti-ciclo — la direccion es cost_analytics -> cost_signals."""
    assert "cost_analytics" not in " ".join(
        _imports_de(BACKEND_ROOT / "services/cost_signals.py"))


def test_cost_stats_no_importa_db_ni_models():
    """Pureza de F1: se testea sin levantar una base."""
    mods = _imports_de(BACKEND_ROOT / "services/cost_stats.py")
    assert "db" not in mods and "models" not in mods


def test_cost_scoring_no_importa_random_ni_red():
    """Determinismo de F2 (G5): sin azar."""
    mods = _imports_de(BACKEND_ROOT / "services/cost_scoring.py")
    assert "random" not in mods
    assert not (mods & _RED)


def test_requirements_txt_no_cambio():
    """G1 — el archivo sigue teniendo exactamente sus 14 dependencias."""
    txt = (BACKEND_ROOT / "requirements.txt").read_text(encoding="utf-8")
    lineas = [x.strip() for x in txt.splitlines()
              if x.strip() and not x.strip().startswith("#")]
    assert len(lineas) == 14, f"requirements.txt tiene {len(lineas)} deps: {lineas}"
    bajo = txt.lower()
    for prohibida in _PROHIBIDOS:
        assert prohibida not in bajo, f"requirements.txt menciona {prohibida}"


def test_numpy_no_esta_instalado_en_el_venv():
    """C22 — la evidencia correcta: numpy no esta ni en el venv ni en el deploy.
    Si algun dia alguien lo instalara, este test avisa ANTES de que un modulo
    del plan empiece a apoyarse en el sin querer."""
    import importlib.util
    assert importlib.util.find_spec("numpy") is None
