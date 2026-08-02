"""Plan 291 — El commit del agente crea la rama que necesita (GitLab).

F1  branch_exists / _default_branch_name (+ F1.b: api/ delega en el provider)
F2  _detect_commit_action deja de confundir "no hay rama" con "no hay archivo"
F3  registro de las TRES flags (dos OFF por (B), una ON)
F4  start_branch en el body del POST, detrás de la flag

CERO RED. Todo va contra dobles: el provider se instancia con __new__ (sin
__init__, o sea sin TLS ni cliente HTTP) y el cliente se falsea.
"""
from __future__ import annotations

import base64
import urllib.parse
from unittest.mock import MagicMock

import pytest

from services.tracker_provider import TrackerApiError


# ── Doble del cliente: idioma exacto de tests/test_plan73_repo_writer.py:11-21 ──

def _provider_con_doble():
    from services.gitlab_provider import GitLabTrackerProvider
    p = GitLabTrackerProvider.__new__(GitLabTrackerProvider)   # sin __init__: cero red, cero TLS
    p._client = MagicMock()
    p._client._project_path.return_value = "grp%2Fproj"
    p._project = "proj"
    p._group = ""
    p._epics_native = False
    return p, p._client


# ══════════════════════════════════════════════════════════════════════════════
# F1 — branch_exists: preguntar si la rama existe en vez de deducirlo de un 404
# ══════════════════════════════════════════════════════════════════════════════

def test_f1_1_branch_exists_true_y_url_encodeada():
    """F1.1 — 200 → True, y la barra de la rama va URL-encodeada (%2F).

    Sin quote(safe=""), GitLab leería 'stacky/incidencia-12-exec-34' como DOS
    segmentos de path y el GET pegaría en otro endpoint.
    """
    provider, cliente = _provider_con_doble()
    cliente._request.return_value = ({}, {})

    assert provider.branch_exists("stacky/incidencia-12-exec-34") is True

    url = cliente._request.call_args[0][1]
    assert "stacky%2Fincidencia-12-exec-34" in url
    assert "stacky/incidencia-12-exec-34" not in url


def test_f1_2_branch_exists_false_en_404():
    """F1.2 — 404 → False (la rama no existe)."""
    provider, cliente = _provider_con_doble()
    cliente._request.side_effect = TrackerApiError(404, "not found", kind="not_found")

    assert provider.branch_exists("stacky/x") is False


def test_f1_3_branch_exists_propaga_403():
    """F1.3 — 401/403/500 NO es 'no existe': se PROPAGA.

    Tratarlo como False haría que commit_file intentara crear una rama que
    quizás ya está (C1 del plan 73).
    """
    provider, cliente = _provider_con_doble()
    cliente._request.side_effect = TrackerApiError(403, "forbidden", kind="auth")

    with pytest.raises(TrackerApiError) as exc:
        provider.branch_exists("stacky/x")
    assert exc.value.status == 403


def test_f1_4_default_branch_name_lee_master_no_adivina_main():
    """F1.4 — la rama base se LEE de /projects/:id, no se adivina."""
    provider, cliente = _provider_con_doble()
    cliente._request.return_value = ({"default_branch": "master"}, {})

    assert provider._default_branch_name() == "master"


def test_f1_5_default_branch_name_repo_vacio_devuelve_cadena_vacia():
    """F1.5 — repo sin rama default (vacío) → "" (F4 lo traduce a repo_empty)."""
    provider, cliente = _provider_con_doble()
    cliente._request.return_value = ({}, {})

    assert provider._default_branch_name() == ""


# ── F1.b — api/devops_production._default_branch DELEGA en el provider ────────

class _ProviderDoble:
    """Doble mínimo de un provider GitLab: expone SOLO _default_branch_name.

    Deliberadamente NO expone `_client`: si `_default_branch` siguiera haciendo
    el GET por su cuenta, el test explota con AttributeError. Eso es el rojo.
    """

    name = "gitlab"

    def __init__(self, rama):
        self._rama = rama

    def _default_branch_name(self):
        return self._rama


def test_f1_6_devops_production_default_branch_delega_en_el_provider():
    """F1.b / F1.6 — la implementación única vive en el provider."""
    from api.devops_production import _default_branch

    assert _default_branch(_ProviderDoble("develop"), "P") == "develop"


def test_f1_7_devops_production_preserva_el_fallback_historico_main():
    """F1.b / F1.7 — con "" del provider, el helper de api/ sigue devolviendo
    'main'. Guarda la PRESENCIA del contrato histórico, que es justo lo que un
    refactor descuidado rompería."""
    from api.devops_production import _default_branch

    assert _default_branch(_ProviderDoble(""), "P") == "main"


# ══════════════════════════════════════════════════════════════════════════════
# F2 — _detect_commit_action deja de confundir "no hay rama" con "no hay archivo"
# ══════════════════════════════════════════════════════════════════════════════

def test_f2_1_rama_inexistente_devuelve_el_sentinela_no_create():
    """F2.1 — rama_existe=False → (_ACCION_RAMA_NUEVA, None), explícitamente NO "create".

    Un 404 del endpoint de ARCHIVOS cuando la rama no existe no prueba nada
    sobre el archivo: traducirlo a "create" es el diagnóstico equivocado.
    """
    provider, _cliente = _provider_con_doble()

    accion, contenido = provider._detect_commit_action("a.py", "stacky/x", rama_existe=False)

    assert accion == "create_new_branch"
    assert accion != "create"
    assert contenido is None


def test_f2_2_rama_inexistente_no_hace_el_get_inutil():
    """F2.2 — con rama_existe=False no se llama a _request ni una vez."""
    provider, cliente = _provider_con_doble()

    provider._detect_commit_action("a.py", "stacky/x", rama_existe=False)

    assert cliente._request.call_count == 0


def test_f2_3_rama_existente_con_404_de_archivo_sigue_siendo_create():
    """F2.3 — NO-REGRESIÓN: rama_existe=True y 404 del archivo → ("create", None).

    Guarda la PRESENCIA del comportamiento de hoy.
    """
    provider, cliente = _provider_con_doble()
    cliente._request.side_effect = TrackerApiError(404, "not found", kind="not_found")

    assert provider._detect_commit_action("a.py", "main", rama_existe=True) == ("create", None)


def test_f2_4_caller_viejo_sin_el_keyword_se_comporta_igual_que_hoy():
    """F2.4 — NO-REGRESIÓN: sin pasar rama_existe (caller viejo) → ("update", contenido).

    Retro-compatibilidad probada, no prometida.
    """
    provider, cliente = _provider_con_doble()
    encoded = base64.b64encode("hola".encode()).decode()
    cliente._request.return_value = ({"content": encoded}, {})

    assert provider._detect_commit_action("a.py", "main") == ("update", "hola")


# ══════════════════════════════════════════════════════════════════════════════
# F3 — Las TRES flags: dos OFF por excepción (B), una ON
# ══════════════════════════════════════════════════════════════════════════════

_K_START_BRANCH = "STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED"
_K_SCAN = "STACKY_AUTOCOMMIT_SECRET_SCAN_ENABLED"
_K_REDACT = "STACKY_AUTOCOMMIT_REDACT_ENABLED"
_LAS_TRES = (_K_START_BRANCH, _K_SCAN, _K_REDACT)


def test_f3_1_las_tres_keys_estan_registradas_como_bool():
    """F3.1 — las tres existen en FLAG_REGISTRY y son booleanas."""
    from services.harness_flags import _REGISTRY_INDEX

    for k in _LAS_TRES:
        spec = _REGISTRY_INDEX.get(k)
        assert spec is not None, f"{k} no está en FLAG_REGISTRY"
        assert spec.type == "bool", f"{k}: type={spec.type}"


def test_f3_2_start_branch_nace_apagada_en_el_default_efectivo():
    """F3.2 — el default EFECTIVO es config.py, no la FlagSpec.

    Es lo único de este plan que hace que Stacky ESCRIBA en el GitLab real del
    operador: nace OFF por la excepción (B).
    """
    import config

    assert getattr(config.config, _K_START_BRANCH) is False


def test_f3_3_el_aviso_nace_encendido_y_el_tapado_apagado():
    """F3.3 — 🔴 GUARDIÁN DEL BLOQUEANTE C1.

    Detectar y avisar va ON (solo lee, no cambia un byte). Enmascarar va OFF:
    cambia los bytes que se escriben en el repositorio real del operador, y el
    camino de Azure DevOps ya está vivo hoy. Si alguien vuelve a poner el
    enmascarado en ON, este test se pone rojo.
    """
    import config

    assert getattr(config.config, _K_SCAN) is True
    assert getattr(config.config, _K_REDACT) is False


def test_f3_4_solo_la_flag_on_declara_default_en_su_flagspec():
    """F3.4 — mecánica dura: una flag OFF NO declara default= (ni default=False),
    porque default_is_known(spec) es literalmente `spec.default is not None` y
    test_default_known_only_for_curated exige que ese conjunto sea EXACTAMENTE
    _CURATED_DEFAULTS_ON."""
    from services.harness_flags import _REGISTRY_INDEX, default_is_known

    for k in (_K_START_BRANCH, _K_REDACT):
        spec = _REGISTRY_INDEX[k]
        assert spec.default is None, f"{k} no debe declarar default="
        assert default_is_known(spec) is False, f"{k}: default_is_known debe ser False"

    spec_scan = _REGISTRY_INDEX[_K_SCAN]
    assert spec_scan.default is True
    assert default_is_known(spec_scan) is True


def test_f3_5_ninguna_declara_requires_y_el_grafo_sigue_sano():
    """F3.5 — ninguna puede declarar requires=:

    · STACKY_GITLAB_ENABLED NO está en FLAG_REGISTRY  → rompería R1.
    · STACKY_INCIDENT_DEV_PR_ENABLED ya tiene requires → rompería R4 (profundidad 1).
    """
    from services.harness_flags import _REGISTRY_INDEX, validate_requires_graph

    for k in _LAS_TRES:
        assert _REGISTRY_INDEX[k].requires is None, f"{k} no debe declarar requires="
    assert validate_requires_graph() == []


def test_f3_6_las_tres_tienen_ayuda_llana_con_el_formato_exigido():
    """F3.6 — PLAIN_HELP no se deriva de description: es un diccionario aparte."""
    from services.harness_flags_help import PLAIN_HELP

    for k in _LAS_TRES:
        entrada = PLAIN_HELP.get(k)
        assert entrada is not None, f"{k} sin ayuda llana"
        assert entrada.on_effect.startswith("Si "), f"{k}: on_effect no empieza con 'Si '"
        assert entrada.off_effect.startswith("Si "), f"{k}: off_effect no empieza con 'Si '"
        assert len(entrada.what.strip()) >= 10, f"{k}: what demasiado corto"
        assert len(entrada.what) <= 200, f"{k}: what > 200"
        assert len(entrada.on_effect) <= 240, f"{k}: on_effect > 240"
        assert len(entrada.off_effect) <= 240, f"{k}: off_effect > 240"
        assert len(entrada.example) <= 300, f"{k}: example > 300"
        for campo in (entrada.what, entrada.on_effect, entrada.off_effect, entrada.example):
            assert campo.strip(), f"{k}: campo vacío"


def test_f3_7_las_entradas_nuevas_no_violan_el_denylist_de_jerga():
    """F3.7 — 🔴 EXISTE PORQUE UN CONTEO SOBRE UN ARCHIVO YA ROJO NO DISCRIMINA.

    tests/test_harness_flags_help.py está en 4 failed / 4 passed de fábrica: si
    estas tres entradas violaran el denylist, ese archivo seguiría en 4 failed
    y nadie se enteraría. Acá se asserta sobre las TRES keys concretas,
    importando el denylist REAL del propio test para que no se desincronice.
    """
    import re

    from test_harness_flags_help import JARGON_DENYLIST, _KEY_RE, _PHASE_RE
    from services.harness_flags_help import PLAIN_HELP

    violaciones = []
    for k in _LAS_TRES:
        entrada = PLAIN_HELP[k]
        for campo in (entrada.what, entrada.on_effect, entrada.off_effect, entrada.example):
            for termino in JARGON_DENYLIST:
                if re.search(rf"\b{re.escape(termino)}s?\b", campo, re.IGNORECASE):
                    violaciones.append(f"{k}: jerga '{termino}'")
            if _KEY_RE.search(campo):
                violaciones.append(f"{k}: cita una key SCREAMING_SNAKE")
            if _PHASE_RE.search(campo):
                violaciones.append(f"{k}: referencia a fase de plan")
    assert violaciones == [], f"Ayuda llana con jerga prohibida: {violaciones}"


# ══════════════════════════════════════════════════════════════════════════════
# F4 — start_branch en el body, detrás de la flag
# ══════════════════════════════════════════════════════════════════════════════

class ClienteFalso:
    """Doble del cliente GitLab CON ESTADO. Cero red.

    ⚠️ EL ESTADO ES EL PUNTO. Un MagicMock plano que devolviera 404 siempre haría
    que el SEGUNDO commit también mandara `start_branch` y F4.1 pasaría igual:
    falso verde en el criterio central de la fase. Acá la rama pasa a EXISTIR
    después del primer POST, que es lo que hace GitLab de verdad.
    """

    def __init__(self, ramas=(), archivos=None, default_branch="main"):
        self.ramas = set(ramas)
        self.archivos = dict(archivos or {})   # (rama, path) -> contenido
        self.default_branch = default_branch
        self.posts = []                        # [(url, json_body)] — LO QUE SE ASERTA

    def _project_path(self):
        return "grp%2Fproj"

    def _request(self, method, path, *, params=None, json_body=None, files=None, _retry=0):
        if method == "GET" and "/repository/branches/" in path:
            rama = urllib.parse.unquote(path.rsplit("/", 1)[1])
            if rama in self.ramas:
                return {"name": rama}, {}
            raise TrackerApiError(404, "branch not found", kind="not_found")

        if method == "GET" and "/repository/files/" in path:
            rel = urllib.parse.unquote(path.rsplit("/", 1)[1])
            rama = (params or {}).get("ref")
            contenido = self.archivos.get((rama, rel))
            if contenido is None:
                raise TrackerApiError(404, "file not found", kind="not_found")
            return {"content": base64.b64encode(contenido.encode()).decode()}, {}

        if method == "GET" and path == f"/projects/{self._project_path()}":
            return {"default_branch": self.default_branch}, {}

        if method == "POST" and path.endswith("/repository/commits"):
            self.posts.append((path, json_body))
            self.ramas.add(json_body["branch"])          # ← la rama pasa a EXISTIR
            for a in json_body["actions"]:
                self.archivos[(json_body["branch"], a["file_path"])] = a["content"]
            return {"id": "deadbeef", "web_url": "http://x/commit/deadbeef"}, {}

        raise AssertionError(f"llamada inesperada: {method} {path}")


def _provider_con_cliente_falso(cliente):
    from services.gitlab_provider import GitLabTrackerProvider
    p = GitLabTrackerProvider.__new__(GitLabTrackerProvider)
    p._client = cliente
    p._project = "proj"
    p._group = ""
    p._epics_native = False
    return p


def _flag_start_branch(monkeypatch, valor):
    """No se toca os.environ: `config = Config()` se instancia en el import y
    os.getenv ya corrió. Se parchea la instancia viva, que es lo que lee el código."""
    import config
    monkeypatch.setattr(
        config.config, "STACKY_GITLAB_COMMIT_START_BRANCH_ENABLED", valor, raising=False,
    )


def test_f4_1_el_primer_post_lleva_start_branch_y_el_segundo_no(monkeypatch):
    """F4.1 — el criterio central. start_branch NO es idempotente: mandarlo en el
    segundo commit sobre una rama que ya existe puede hacer que GitLab rechace la
    operación o cree un commit huérfano."""
    _flag_start_branch(monkeypatch, True)
    cliente = ClienteFalso(ramas=(), default_branch="main")
    provider = _provider_con_cliente_falso(cliente)

    provider.commit_file("src/a.py", "uno", "stacky/incidencia-12-exec-34", "msg")
    provider.commit_file("src/b.py", "dos", "stacky/incidencia-12-exec-34", "msg")

    assert len(cliente.posts) == 2
    assert "start_branch" in cliente.posts[0][1]
    assert "start_branch" not in cliente.posts[1][1]


def test_f4_2_la_rama_base_se_lee_no_se_adivina(monkeypatch):
    """F4.2 — si el repo usa 'develop', start_branch dice 'develop'. Nunca 'main'."""
    _flag_start_branch(monkeypatch, True)
    cliente = ClienteFalso(ramas=(), default_branch="develop")
    provider = _provider_con_cliente_falso(cliente)

    provider.commit_file("src/a.py", "uno", "stacky/x", "msg")

    assert cliente.posts[0][1]["start_branch"] == "develop"


def test_f4_3_con_la_flag_apagada_cero_post_y_error_accionable(monkeypatch):
    """F4.3 — flag OFF + rama inexistente → TrackerApiError(kind='branch_missing')
    y CERO POST al endpoint de commits.

    ⚠️ "cero POST" no es "cero escritura" a nivel sistema: el camino de error del
    auto-PR igual comenta en la Issue (plan 291 §3.7 / R12). Acá se afirma lo
    primero, que es lo que esta fase gobierna.
    """
    _flag_start_branch(monkeypatch, False)
    cliente = ClienteFalso(ramas=(), default_branch="main")
    provider = _provider_con_cliente_falso(cliente)

    with pytest.raises(TrackerApiError) as exc:
        provider.commit_file("src/a.py", "uno", "stacky/x", "msg")

    assert exc.value.kind == "branch_missing"
    assert "stacky/x" in str(exc.value)
    assert cliente.posts == []


def test_f4_4_rama_preexistente_nunca_lleva_start_branch(monkeypatch):
    """F4.4 — con la rama ya creada de antes, el body es el de hoy."""
    _flag_start_branch(monkeypatch, True)
    cliente = ClienteFalso(ramas={"stacky/x"}, default_branch="main")
    provider = _provider_con_cliente_falso(cliente)

    provider.commit_file("src/a.py", "uno", "stacky/x", "msg")

    assert "start_branch" not in cliente.posts[0][1]


def test_f4_5_repo_vacio_da_error_claro_y_cero_post(monkeypatch):
    """F4.5 — sin rama default no hay desde dónde crear: repo_empty, antes del POST."""
    _flag_start_branch(monkeypatch, True)
    cliente = ClienteFalso(ramas=(), default_branch="")
    provider = _provider_con_cliente_falso(cliente)

    with pytest.raises(TrackerApiError) as exc:
        provider.commit_file("src/a.py", "uno", "stacky/x", "msg")

    assert exc.value.kind == "repo_empty"
    assert cliente.posts == []


def test_f4_6_el_corto_de_contenido_identico_se_preserva(monkeypatch):
    """F4.6 — FIX C7 del plan 73 intacto: mismo contenido → 'unchanged' sin POST."""
    _flag_start_branch(monkeypatch, True)
    cliente = ClienteFalso(
        ramas={"stacky/x"}, archivos={("stacky/x", "src/a.py"): "uno"}, default_branch="main",
    )
    provider = _provider_con_cliente_falso(cliente)

    resultado = provider.commit_file("src/a.py", "uno", "stacky/x", "msg")

    assert resultado["status"] == "unchanged"
    assert cliente.posts == []


def test_f4_7_el_radio_de_la_flag_alcanza_al_armado_de_pipelines(monkeypatch):
    """F4.7 — RADIO DE ALCANCE DECLARADO (§3.6), PROBADO.

    La perilla vive en commit_file, no en el auto-PR: commit_file tiene TRES
    consumidores y api/pipeline_generator.py:97 arma ramas `feature/pipeline-…`.
    Este test NO afirma que eso esté mal: afirma que PASA, para que el radio real
    quede escrito en el arnés y no solo en la prosa del plan.

    (El F4.7 del v1 asertaba `branch.startswith("stacky/")` sobre ramas que el
    propio test pasaba: un gate que comprueba su propio input. El K2 de verdad
    vive en F6.8, que ejecuta el producto.)
    """
    _flag_start_branch(monkeypatch, True)
    cliente = ClienteFalso(ramas=(), default_branch="main")
    provider = _provider_con_cliente_falso(cliente)

    provider.commit_file(".gitlab-ci.yml", "stages: []", "feature/pipeline-x", "msg")

    assert cliente.posts[0][1]["branch"] == "feature/pipeline-x"
    assert "start_branch" in cliente.posts[0][1]
