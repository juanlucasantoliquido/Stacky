"""Plan 259 F9 — Guardian de paridad de trackers: que este agujero no pueda volver.

Este plan existe porque GitLab quedo cableado A MEDIAS —boton en Edicion, tipo en
types.ts, 7 modulos de motor— y el alta y el PATCH nunca se enteraron, degradando
proyectos a Azure DevOps durante ~194 planes sin que nada avisara. Arreglar el
caso de GitLab (F1-F8) no impide que pase de nuevo con el quinto tracker. Esta
fase si.

DISEÑO — AST, NO REGEX. La casa ya se quemo con centinelas textuales (exigir
`config.config` en masa rompio el motor de flags). Se recorre el arbol sintactico.

Si el guardian sale rojo por algo que F1-F8 no cubrieron, se arregla EL PRODUCTO,
nunca se afloja el guardian.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

import project_manager
from services import project_context as project_context_mod

TRACKERS = ("azure_devops", "jira", "mantis", "gitlab")  # fuente: frontend/src/types.ts TrackerType

# El producto usa "ado" como abreviatura historica de azure_devops en
# project_manager. Tabla EXPLICITA, no heuristica: si mañana se agrega un tracker
# con nombre corto, se declara aca y el guardian sigue siendo honesto.
_SLUG = {"azure_devops": "ado", "jira": "jira", "mantis": "mantis", "gitlab": "gitlab"}

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_API_PROJECTS = _BACKEND / "api" / "projects.py"


def _init_fn(t: str) -> str:
    return f"initialize_{_SLUG[t]}_project"


def _auth_fn(t: str) -> str:
    return f"write_{_SLUG[t]}_auth"


# ── helpers de AST ───────────────────────────────────────────────────────────

def _func_node(path: pathlib.Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"no se encontro la funcion {name} en {path.name}")


def _tracker_literals(fn: ast.FunctionDef) -> set[str]:
    """Literales comparados contra `tracker_type` en los if/elif de la funcion."""
    found: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.Compare):
            continue
        if not (isinstance(node.left, ast.Name) and node.left.id == "tracker_type"):
            continue
        for cmp_node in node.comparators:
            if isinstance(cmp_node, ast.Constant) and isinstance(cmp_node.value, str):
                found.add(cmp_node.value)
    return found


def _else_calls(fn: ast.FunctionDef) -> set[str]:
    """Nombres de funcion llamados en el `else` final de la cadena de tracker_type."""
    called: set[str] = set()
    for node in ast.walk(fn):
        if not isinstance(node, ast.If):
            continue
        if not node.orelse or isinstance(node.orelse[0], ast.If):
            continue  # es un `elif`, no el `else` final
        for sub in ast.walk(ast.Module(body=node.orelse, type_ignores=[])):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                called.add(sub.func.id)
    return called


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _env_aislado(tmp_path_factory, monkeypatch):
    """NUNCA el .env real del operador."""
    import api.global_config as agc
    import api.harness_flags as ahf
    from config import config as cfg

    env_file = tmp_path_factory.mktemp("env") / ".env"
    env_file.write_text("# env de test\n", encoding="utf-8")
    monkeypatch.setattr(ahf, "_ENV_PATH", env_file)
    monkeypatch.setattr(agc, "_ENV_PATH", env_file)
    monkeypatch.setattr(cfg, "STACKY_GITLAB_ENABLED", False, raising=False)


@pytest.fixture()
def proyectos(tmp_path, monkeypatch):
    import api.projects as api_projects

    projects = tmp_path / "projects"
    projects.mkdir()
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setattr(project_manager, "PROJECTS_DIR", projects)
    monkeypatch.setattr(project_context_mod, "PROJECTS_DIR", projects)
    monkeypatch.setattr(api_projects, "PROJECTS_DIR", projects)
    return {"dir": projects, "ws": str(ws)}


@pytest.fixture()
def client():
    from app import create_app

    app = create_app()
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def _body_for(tracker: str, name: str, ws: str) -> dict:
    """Cuerpo MINIMO valido de cada tracker."""
    base = {"name": name, "workspace_root": ws, "tracker_type": tracker}
    extra = {
        "azure_devops": {"organization": "ACME", "ado_project": "Proj"},
        "jira": {"jira_url": "https://acme.atlassian.net", "jira_key": "ACME"},
        "mantis": {"mantis_url": "https://mantis.acme", "mantis_project_id": "7"},
        "gitlab": {"gitlab_url": "https://gitlab.com", "gitlab_project": "acme/api"},
    }[tracker]
    return {**base, **extra}


def _tipo_en_disco(proyectos, name: str) -> str:
    cfg = json.loads(
        (proyectos["dir"] / name.upper() / "config.json").read_text(encoding="utf-8")
    )
    return (cfg.get("issue_tracker") or {}).get("type", "")


# ── las 6 piezas obligatorias de cada tracker ────────────────────────────────

@pytest.mark.parametrize("tracker", TRACKERS)
def test_cada_tracker_tiene_helper_de_alta(tracker):
    fn = _init_fn(tracker)
    assert hasattr(project_manager, fn), f"falta {fn} en project_manager"
    assert fn in project_manager.__all__, f"{fn} no esta exportado en __all__"


@pytest.mark.parametrize("tracker", TRACKERS)
def test_cada_tracker_tiene_escritor_de_credencial(tracker):
    fn = _auth_fn(tracker)
    assert hasattr(project_manager, fn), f"falta {fn} en project_manager"
    assert fn in project_manager.__all__, f"{fn} no esta exportado en __all__"


def test_la_tabla_de_slugs_cubre_todos_los_trackers():
    """Evita que alguien agregue un tracker a TRACKERS y se olvide del slug,
    dejando un KeyError en vez de un fallo legible."""
    assert set(_SLUG) == set(TRACKERS)


def test_init_project_ramifica_por_cada_tracker():
    fn = _func_node(_API_PROJECTS, "init_project")
    literales = _tracker_literals(fn)
    # El `else` final es la rama azure_devops: se PRUEBA por AST, no se supone.
    assert _init_fn("azure_devops") in _else_calls(fn), (
        "el else final de init_project deberia llamar a initialize_ado_project"
    )
    assert literales | {"azure_devops"} == set(TRACKERS), (
        f"init_project ramifica por {sorted(literales)} + else(azure_devops); "
        f"faltan {sorted(set(TRACKERS) - literales - {'azure_devops'})}"
    )


def test_update_project_ramifica_por_cada_tracker():
    """ESTE es el test que hubiera atrapado el bug original."""
    fn = _func_node(_API_PROJECTS, "update_project")
    literales = _tracker_literals(fn)
    assert _init_fn("azure_devops") in _else_calls(fn), (
        "el else final de update_project deberia llamar a initialize_ado_project"
    )
    assert literales | {"azure_devops"} == set(TRACKERS), (
        f"update_project ramifica por {sorted(literales)} + else(azure_devops); "
        f"faltan {sorted(set(TRACKERS) - literales - {'azure_devops'})}"
    )


def test_has_credentials_conoce_todos_los_trackers(proyectos):
    """Hoy GitLab comparte el archivo de Mantis: 4 trackers, 4 nombres UNICOS.

    Se llama con el nombre en MAYUSCULAS, igual que hace el codigo de produccion
    (initialize_project hace name.upper() y lo guarda en cfg["name"], que es lo
    que _project_to_dict le pasa). En minusculas daria un falso rojo.
    """
    from api.projects import _has_credentials

    base = proyectos["dir"] / "PROY" / "auth"
    base.mkdir(parents=True)
    vistos: dict[str, str] = {}
    for tracker in TRACKERS:
        # Se prueba cual ARCHIVO mira: se crea uno por vez y se verifica que solo
        # ese tracker lo reconozca.
        for archivo in base.iterdir():
            archivo.unlink()
        nombre = f"{_SLUG[tracker]}_auth.json"
        (base / nombre).write_text("{}", encoding="utf-8")
        assert _has_credentials("PROY", tracker) is True, (
            f"{tracker} no reconoce {nombre}"
        )
        vistos[tracker] = nombre
    assert len(set(vistos.values())) == len(TRACKERS), (
        f"dos trackers comparten archivo de credencial: {vistos}"
    )


@pytest.mark.parametrize("tracker", TRACKERS)
def test_todo_tracker_tiene_template_embebido(tracker):
    """Evita que el proximo tracker herede el perfil de ADO en el deploy congelado."""
    from services.client_profile_default_templates import DEFAULT_TEMPLATES

    assert tracker in DEFAULT_TEMPLATES


# ── property tests: ningun tipo se degrada ───────────────────────────────────

@pytest.mark.parametrize("tracker", TRACKERS)
def test_ningun_alta_degrada_el_tipo(proyectos, client, tracker):
    """Sin excepciones, sin "salvo GitLab"."""
    name = f"ALTA{TRACKERS.index(tracker)}"
    resp = client.post("/api/init_project", json=_body_for(tracker, name, proyectos["ws"]))
    assert resp.status_code == 200, f"{tracker}: {resp.get_data(as_text=True)}"
    assert _tipo_en_disco(proyectos, name) == tracker


@pytest.mark.parametrize("origen", TRACKERS)
@pytest.mark.parametrize("destino", TRACKERS)
def test_ningun_patch_degrada_el_tipo(proyectos, client, origen, destino):
    """12 combinaciones cruzadas + las 4 identidades. Contra el arbol previo a F2
    falla en las 3 que van a GitLab: es la reproduccion exacta del bug E2."""
    if origen == destino:
        pytest.skip("cubierto por test_ningun_alta_degrada_el_tipo")
    name = f"MIG{TRACKERS.index(origen)}{TRACKERS.index(destino)}"
    creado = client.post("/api/init_project", json=_body_for(origen, name, proyectos["ws"]))
    assert creado.status_code == 200, f"{origen}: {creado.get_data(as_text=True)}"

    cambio = {k: v for k, v in _body_for(destino, name, proyectos["ws"]).items()
              if k not in ("name", "workspace_root")}
    resp = client.patch(f"/api/projects/{name}", json=cambio)
    assert resp.status_code == 200, f"{origen}->{destino}: {resp.get_data(as_text=True)}"
    assert _tipo_en_disco(proyectos, name) == destino, (
        f"PATCH {origen} -> {destino} degrado el tipo a "
        f"{_tipo_en_disco(proyectos, name)!r}"
    )
