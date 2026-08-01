"""Plan 279 F7 — Tests de variables faltantes POR NOMBRE.

6 casos. K3: el VALOR de un secreto no existe en el camino del copiloto, y eso
se prueba con un test, no con una promesa.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from services.pipeline_copilot_prompt import build_copilot_prompt
from services.pipeline_copilot_secrets import required_variable_names, secret_names
from services.pipeline_session import PipelineSession

_MODULE_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "services" / "pipeline_copilot_secrets.py"
)

#: El valor que NUNCA puede salir del provider. Si aparece en el prompt, K3 cayo.
VALOR_DE_PRUEBA = "valor-secreto-de-prueba"

#: Spec que referencia 3 variables por sus nombres, al estilo ADO ($(VAR)).
_SPEC = {
    "stages": [{
        "name": "build",
        "jobs": [{
            "name": "compilar",
            "steps": [
                {"script": "echo $(DB_PASSWORD) && echo $(API_TOKEN)"},
                {"script": "deploy --host $(DEPLOY_HOST)"},
            ],
        }],
    }],
}


class _ProviderFalso:
    """Espeja el sub-puerto: list_variables() NUNCA devuelve `value`."""

    name = "falso"

    def __init__(self, keys):
        self._keys = list(keys)

    def list_variables(self):
        from services.ci_variables import looks_secret

        return [
            {"key": k, "is_secret": looks_secret(k), "has_value": True, "masked": True}
            for k in self._keys
        ]


class _ProviderQueExplota:
    name = "explota"

    def list_variables(self):
        raise RuntimeError("el tracker no responde")


@pytest.fixture
def provider(monkeypatch):
    """Inyecta el provider por el seam del modulo. Devuelve el setter."""
    import services.pipeline_copilot_secrets as mod

    def _set(obj):
        monkeypatch.setattr(mod, "_get_provider", lambda project: obj)

    return _set


# --------------------------------------------------------------------------


def test_devuelve_solo_las_que_faltan(provider):
    # El proyecto YA define DEPLOY_HOST => no puede figurar como faltante.
    provider(_ProviderFalso(["DEPLOY_HOST"]))
    faltan = required_variable_names(_SPEC, "ado", "ProyectoDePrueba")
    assert "DEPLOY_HOST" not in faltan, faltan
    assert "DB_PASSWORD" in faltan, faltan
    assert "API_TOKEN" in faltan, faltan


def test_ordenado_y_sin_duplicados(provider):
    provider(_ProviderFalso([]))
    faltan = required_variable_names(_SPEC, "ado", "ProyectoDePrueba")
    assert list(faltan) == sorted(set(faltan)), faltan
    assert len(faltan) == len(set(faltan)), faltan


def test_secret_names_usa_looks_secret():
    nombres = ("DB_PASSWORD", "API_TOKEN", "DEPLOY_HOST", "BUILD_NUMBER")
    secretos = secret_names(nombres)
    assert "DB_PASSWORD" in secretos
    assert "API_TOKEN" in secretos
    # Guard discriminante: lo que NO parece secreto queda afuera (si devolviera
    # todo, el assert de arriba pasaria igual).
    assert "DEPLOY_HOST" not in secretos, secretos
    assert "BUILD_NUMBER" not in secretos, secretos
    assert secret_names(()) == ()


def test_el_modulo_no_importa_secrets_store():
    """GATE DE K3, por `ast`. secrets_store devuelve PLAINTEXT
    (resolve_secret_in_payload :204 / read_secret_from_file :258): este modulo
    no puede tenerlo ni al alcance."""
    src = _MODULE_PATH.read_text(encoding="utf-8")
    arbol = ast.parse(src)

    modulos: list[str] = []
    for node in ast.walk(arbol):
        if isinstance(node, ast.ImportFrom) and node.module:
            modulos.append(node.module)
        elif isinstance(node, ast.Import):
            modulos.extend(a.name for a in node.names)

    # GUARD anti-falso-verde: el censo TIENE que ver los imports que si estan.
    assert modulos, "el censo de imports dio vacio: gate invalido"
    assert any("ci_variables" in m for m in modulos), modulos

    ofensores = [m for m in modulos if "secrets_store" in m]
    assert ofensores == [], ofensores


def test_ningun_valor_llega_al_prompt(provider):
    """K3 de punta a punta: del provider al prompt del modelo."""
    falso = _ProviderFalso(["DEPLOY_HOST"])
    # Inyectamos el valor EN EL FIXTURE, para poder probar que no viaja.
    for fila in falso.list_variables():
        fila["value"] = VALOR_DE_PRUEBA

    # GUARD OBLIGATORIO, PRIMERO: el valor SI esta en el fixture. Sin esto, un
    # fixture vacio haria pasar el assert de ausencia por accidente.
    filas = falso.list_variables()
    for fila in filas:
        fila["value"] = VALOR_DE_PRUEBA
    assert any(f.get("value") == VALOR_DE_PRUEBA for f in filas), (
        "el fixture no contiene el valor de prueba: el assert de ausencia de "
        "abajo pasaria vacio"
    )

    provider(falso)
    faltan = required_variable_names(_SPEC, "ado", "ProyectoDePrueba")
    assert faltan, "sin variables faltantes el test no discrimina"

    prompt = build_copilot_prompt(
        PipelineSession(state="secrets", missing_variables=faltan),
        "http://localhost:5000", "que me falta?", 1, commit_enabled=False,
    )
    # Los NOMBRES si viajan (son handles).
    for nombre in faltan:
        assert nombre in prompt, nombre
    # El VALOR, jamas.
    assert VALOR_DE_PRUEBA not in prompt, "un valor de secreto llego al prompt"


def test_error_del_provider_degrada_a_tupla_vacia(provider):
    provider(_ProviderQueExplota())
    assert required_variable_names(_SPEC, "ado", "ProyectoDePrueba") == ()
    # Y tampoco lanza con una spec basura.
    assert required_variable_names(None, "ado", "P") == ()  # type: ignore[arg-type]
    assert required_variable_names({}, "gitlab", "") == ()
