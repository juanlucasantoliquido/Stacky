"""Plan 289 — El agente deja de trabajar a ciegas sobre un ticket de GitLab.

PATA A (xfail hasta F6): con un proyecto GitLab, el enriquecimiento produce el
  bloque de comentarios con las notas del issue.
PATA B (xfail hasta F2): los 3 runtimes persisten el contador de enriquecimiento.

NO importa db, ni app, ni models (P6). El ticket es un SimpleNamespace y el
provider es un doble local.
"""
from __future__ import annotations

import ast
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# -- Dobles -------------------------------------------------------------------

NOTAS_GITLAB = [
    {"id": 11, "body": "Primera nota del cliente", "system": False,
     "author": {"name": "Ana Perez", "username": "aperez"},
     "created_at": "2026-07-30T10:11:12.000Z"},
    {"id": 12, "body": "Segunda nota con detalle", "system": False,
     "author": {"name": "Beto Diaz", "username": "bdiaz"},
     "created_at": "2026-07-31T09:00:00.000Z"},
    {"id": 13, "body": "Tercera nota", "system": False,
     "author": {"name": "Ana Perez", "username": "aperez"},
     "created_at": "2026-08-01T08:00:00.000Z"},
]


class _FakeGitLabProvider:
    name = "gitlab"

    def __init__(self, notas):
        self._notas = notas
        self.llamadas = []

    def fetch_comments(self, item_id):          # firma REAL de GitLab: SIN top
        self.llamadas.append(item_id)
        return list(self._notas)


def _ctx_gitlab():
    """Doble de ProjectContext con tracker gitlab."""
    return types.SimpleNamespace(
        stacky_project_name="GITLABTEST", tracker_type="gitlab",
        tracker_project="grupo/proyecto", organization=None,
        base_url="https://gitlab.interno", tracker_group="grupo",
        workspace_root=None, auth_path=None, vscode_port=None,
    )


@pytest.fixture
def proyecto_gitlab(monkeypatch):
    """Fija el contexto de proyecto a uno GitLab y devuelve el provider falso.

    Parchea LOS DOS seams por separado a proposito:
      - resolve_project_context: lo consume build_ado_client (project_context.py:510)
      - get_tracker_provider:    lo consumira el dispatcher de F6
    """
    import services.project_context as pc
    import services.tracker_provider as tp

    fake = _FakeGitLabProvider(NOTAS_GITLAB)
    monkeypatch.setattr(pc, "resolve_project_context", lambda *a, **k: _ctx_gitlab())
    monkeypatch.setattr(tp, "get_tracker_provider", lambda project=None: fake)
    return fake


# -- PATA A - el bloque que hoy no existe (verde en F6) -----------------------

# F6 (2026-08-02): el marcador `xfail(strict=True)` se RETIRA en el mismo commit que
# enciende el dispatcher. Con strict=True dejarlo daria XPASS(strict) = FAILED.
def test_un_issue_de_gitlab_con_3_notas_produce_un_bloque_con_las_3(proyecto_gitlab):
    from services.ado_context import build_ado_context_blocks

    ticket = types.SimpleNamespace(
        ado_id=1124, external_id=1124, stacky_project_name="GITLABTEST",
        tracker_type="gitlab", project="grupo/proyecto",
    )
    blocks, stats = build_ado_context_blocks(
        1124, project_name="GITLABTEST", tracker_project="grupo/proyecto", ticket=ticket,
    )

    comentarios = [b for b in blocks if b.get("id") == "ado-comments"]
    assert len(comentarios) == 1, f"esperaba 1 bloque de comentarios, hay {len(comentarios)}: {blocks}"
    contenido = comentarios[0]["content"]
    assert "Primera nota del cliente" in contenido
    assert "Segunda nota con detalle" in contenido
    assert "Tercera nota" in contenido
    assert stats["comments_count"] == 3
    # El id que se le pasa al provider es el iid, que vive en ado_id (§4.8).
    assert proyecto_gitlab.llamadas == ["1124"]


# -- PATA B - el contador que se pierde (verde en F2) -------------------------

# v2 / C3 - CONGELADO. Los tres nombres estan VERIFICADOS POR AST el 2026-08-02, no
# asumidos: `_run_in_background` en los tres, y en cada archivo el nombre es UNICO
# (no hay dos funciones con ese nombre, asi que `_funcion_del_modulo` no puede
# devolver la equivocada):
#   agent_runner.py                     :: _run_in_background   lineas 718..1231
#   services/claude_code_cli_runner.py  :: _run_in_background   lineas 595..2179
#   services/codex_cli_runner.py        :: _run_in_background   lineas 258..1260
# NO "verifiques y corregi": ya esta verificado. Si alguna pata de presencia sale
# ROJA, es porque la sesion paralela renombro algo - parala y avisa, no la edites.
_SITIOS_DE_ENRIQUECIMIENTO = (
    ("agent_runner.py", "_run_in_background"),
    ("services/claude_code_cli_runner.py", "_run_in_background"),
    ("services/codex_cli_runner.py", "_run_in_background"),
)


def _funcion_del_modulo(ruta_rel: str, nombre: str):
    """Devuelve el nodo AST de la funcion, o None si no existe.

    Guarda anti-ambiguedad (v2): si hubiera DOS funciones con el mismo nombre en
    el archivo, devolver "la primera" haria que el censo mirase la equivocada.
    Se falla ruidosamente en vez de elegir.
    """
    arbol = ast.parse((ROOT / ruta_rel).read_text(encoding="utf-8"))
    encontradas = [
        n for n in ast.walk(arbol)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nombre
    ]
    assert len(encontradas) <= 1, (
        f"{ruta_rel} tiene {len(encontradas)} funciones llamadas {nombre!r}: el censo "
        f"miraria una arbitraria. Desambigua antes de seguir."
    )
    return encontradas[0] if encontradas else None


def _llama_a(nodo, nombre_funcion: str):
    """Devuelve el nodo ast.Call de la PRIMERA llamada `f(...)` o `mod.f(...)`, o None."""
    for hijo in ast.walk(nodo):
        if not isinstance(hijo, ast.Call):
            continue
        f = hijo.func
        if isinstance(f, ast.Name) and f.id == nombre_funcion:
            return hijo
        if isinstance(f, ast.Attribute) and f.attr == nombre_funcion:
            return hijo
    return None


def _nombre_del_stat_de_enrich(nodo) -> str | None:
    """Nombre local al que se desempaqueta el 2o valor de enrich_blocks(...).

    Busca `a, b = <algo>.enrich_blocks(...)` y devuelve el nombre de `b`.
    """
    for hijo in ast.walk(nodo):
        if not isinstance(hijo, ast.Assign) or not isinstance(hijo.value, ast.Call):
            continue
        f = hijo.value.func
        nombre = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
        if nombre != "enrich_blocks":
            continue
        destino = hijo.targets[0]
        if isinstance(destino, ast.Tuple) and len(destino.elts) == 2:
            segundo = destino.elts[1]
            if isinstance(segundo, ast.Name):
                return segundo.id
    return None


@pytest.mark.parametrize("ruta,funcion", _SITIOS_DE_ENRIQUECIMIENTO)
def test_pata_de_presencia_la_funcion_vigilada_existe(ruta, funcion):
    """Sin esta pata, borrar o renombrar la funcion dejaria el censo verde POR AUSENCIA."""
    assert _funcion_del_modulo(ruta, funcion) is not None, (
        f"{ruta}::{funcion} no existe. El censo de abajo quedaria verde por ausencia, "
        f"no por correccion. NO edites _SITIOS_DE_ENRIQUECIMIENTO sin leer el plan 289 F0."
    )


@pytest.mark.parametrize("ruta,funcion", _SITIOS_DE_ENRIQUECIMIENTO)
def test_pata_de_presencia_la_funcion_llama_al_pipeline(ruta, funcion):
    """La funcion vigilada es, de verdad, la que enriquece."""
    assert _llama_a(_funcion_del_modulo(ruta, funcion), "enrich_blocks") is not None


# -- v2 / C4 - el censo NO se conforma con "que la llamada exista" ------------
# Un censo por presencia de llamada se satisface con
#   persistir_stats_de_contexto(execution_id=None, stats=None)
# o con la llamada metida en una rama muerta: verde, y el contador se sigue
# perdiendo. Este censo exige ADEMAS que los dos kwargs esten y que `stats=`
# reciba EXACTAMENTE el nombre al que se desempaqueto el 2o valor de
# enrich_blocks. Eso es determinista, barato y no se puede fingir sin cablearlo
# de verdad. (Lo que sigue sin cubrir un censo estatico es que la funcion HAGA
# lo suyo: eso lo prueba tests/test_plan289_stat_de_contexto.py, ejecutandola.)

# F2 (2026-08-02): el marcador `xfail(strict=True)` se RETIRA en el mismo commit que
# pone verde la pata. Con strict=True dejarlo daria XPASS(strict) = FAILED.
@pytest.mark.parametrize("ruta,funcion", _SITIOS_DE_ENRIQUECIMIENTO)
def test_los_3_runtimes_persisten_el_contador(ruta, funcion):
    nodo = _funcion_del_modulo(ruta, funcion)
    llamada = _llama_a(nodo, "persistir_stats_de_contexto")
    assert llamada is not None, (
        f"{ruta}::{funcion} llama a enrich_blocks pero no persiste el contador"
    )
    kwargs = {k.arg: k.value for k in llamada.keywords if k.arg}
    assert "execution_id" in kwargs and "stats" in kwargs, (
        f"{ruta}::{funcion} llama al helper sin execution_id= y/o sin stats=: {sorted(kwargs)}"
    )
    esperado = _nombre_del_stat_de_enrich(nodo)
    assert esperado is not None, (
        f"{ruta}::{funcion} ya no desempaqueta enrich_blocks en 2 nombres"
    )
    recibido = getattr(kwargs["stats"], "id", None)
    assert recibido == esperado, (
        f"{ruta}::{funcion} persiste `{recibido}` pero enrich_blocks devolvio `{esperado}`: "
        f"la llamada existe pero NO esta cableada al stat real"
    )


# -- F3 - normalizador puro ---------------------------------------------------

def test_normaliza_una_nota_completa():
    from services.tracker_context import normalizar_notas_gitlab

    out = normalizar_notas_gitlab([NOTAS_GITLAB[0]])
    assert out == [{
        "author": "Ana Perez",
        "date": "2026-07-30",          # created_at recortado a 10, igual que ADO
        "text": "Primera nota del cliente",
        "is_html": False,
    }]


def test_autor_cae_a_username_y_despues_a_interrogacion():
    from services.tracker_context import normalizar_notas_gitlab

    solo_username = {"body": "x", "author": {"username": "cdiaz"}, "created_at": "2026-01-02T00:00:00Z"}
    sin_autor = {"body": "y", "created_at": "2026-01-02T00:00:00Z"}
    autor_no_dict = {"body": "z", "author": "texto suelto", "created_at": ""}
    out = normalizar_notas_gitlab([solo_username, sin_autor, autor_no_dict])
    assert [c["author"] for c in out] == ["cdiaz", "?", "?"]


def test_nota_sin_body_se_descarta():
    from services.tracker_context import normalizar_notas_gitlab

    assert normalizar_notas_gitlab([{"body": "", "author": {"name": "A"}},
                                    {"body": "   ", "author": {"name": "A"}},
                                    {"author": {"name": "A"}}]) == []


def test_nota_system_se_descarta_aunque_el_provider_falle_en_filtrarla():
    """Cinturon y tirantes: el provider ya filtra system, pero el normalizador NO confia."""
    from services.tracker_context import normalizar_notas_gitlab

    assert normalizar_notas_gitlab([{"body": "changed title", "system": True,
                                     "author": {"name": "A"}, "created_at": "2026-01-01T00:00:00Z"}]) == []


def test_created_at_vacio_o_ausente_da_cadena_vacia():
    from services.tracker_context import normalizar_notas_gitlab

    out = normalizar_notas_gitlab([{"body": "x", "author": {"name": "A"}},
                                   {"body": "y", "author": {"name": "A"}, "created_at": None}])
    assert [c["date"] for c in out] == ["", ""]


def test_entrada_que_no_es_lista_de_dicts_no_explota():
    from services.tracker_context import normalizar_notas_gitlab

    assert normalizar_notas_gitlab(None) == []
    assert normalizar_notas_gitlab([]) == []
    assert normalizar_notas_gitlab(["texto", 3, None]) == []


def test_el_orden_de_entrada_se_conserva():
    from services.tracker_context import normalizar_notas_gitlab

    out = normalizar_notas_gitlab(NOTAS_GITLAB)
    assert [c["text"] for c in out] == [
        "Primera nota del cliente", "Segunda nota con detalle", "Tercera nota"]


# -- F4 - lector por proveedor ------------------------------------------------

def test_lee_los_comentarios_por_la_fabrica_y_los_normaliza(proyecto_gitlab):
    from services.tracker_context import fetch_comentarios_normalizados

    comentarios, stats = fetch_comentarios_normalizados(project_name="GITLABTEST", item_id=1124)
    assert [c["text"] for c in comentarios] == [
        "Primera nota del cliente", "Segunda nota con detalle", "Tercera nota"]
    assert stats == {"comments_count": 3, "comments_truncated": False,
                     "comments_total_disponibles": 3, "errors": []}
    assert proyecto_gitlab.llamadas == ["1124"]     # str, y es el iid (§4.8)


def test_el_tope_recorta_y_lo_DECLARA(monkeypatch):
    """Un issue con mas notas que el tope entrega EXACTAMENTE el tope, y lo dice."""
    import services.tracker_provider as tp
    from services.tracker_context import fetch_comentarios_normalizados

    muchas = [{"body": f"nota {i}", "system": False, "author": {"name": "A"},
               "created_at": "2026-01-01T00:00:00Z"} for i in range(200)]
    monkeypatch.setattr(tp, "get_tracker_provider", lambda project=None: _FakeGitLabProvider(muchas))

    comentarios, stats = fetch_comentarios_normalizados(project_name="GITLABTEST", item_id=1)
    assert len(comentarios) == 30                     # el default, = top=30 de ADO
    assert stats["comments_count"] == 30
    assert stats["comments_truncated"] is True
    assert stats["comments_total_disponibles"] == 200   # v2: lo necesita el sello de F5/F6
    # Se quedan las MAS RECIENTES: las notas vienen mas viejas primero (v2 §4.12: ADO
    # las trae al reves, con order=desc; el sentido se DECLARA en el sello, no se invierte).
    assert comentarios[-1]["text"] == "nota 199"
    assert comentarios[0]["text"] == "nota 170"


def test_el_tope_se_puede_bajar_por_env(monkeypatch):
    import services.tracker_provider as tp
    from services.tracker_context import fetch_comentarios_normalizados

    monkeypatch.setenv("TRACKER_CONTEXT_MAX_COMMENTS", "2")
    monkeypatch.setattr(tp, "get_tracker_provider", lambda project=None: _FakeGitLabProvider(NOTAS_GITLAB))
    comentarios, stats = fetch_comentarios_normalizados(project_name="GITLABTEST", item_id=1)
    assert len(comentarios) == 2
    assert stats["comments_truncated"] is True
    assert [c["text"] for c in comentarios] == ["Segunda nota con detalle", "Tercera nota"]


def test_tope_cero_devuelve_cero_comentarios_sin_error(monkeypatch):
    import services.tracker_provider as tp
    from services.tracker_context import fetch_comentarios_normalizados

    monkeypatch.setenv("TRACKER_CONTEXT_MAX_COMMENTS", "0")
    monkeypatch.setattr(tp, "get_tracker_provider", lambda project=None: _FakeGitLabProvider(NOTAS_GITLAB))
    comentarios, stats = fetch_comentarios_normalizados(project_name="GITLABTEST", item_id=1)
    assert comentarios == []
    assert stats["comments_count"] == 0
    assert stats["errors"] == []


def test_el_master_switch_de_gitlab_apagado_se_DECLARA_no_se_confunde(monkeypatch):
    """STACKY_GITLAB_ENABLED=false NO puede reportarse como un error de Azure DevOps."""
    import services.tracker_provider as tp
    from services.tracker_context import fetch_comentarios_normalizados

    def _explota(project=None):
        raise tp.TrackerConfigError("issue_tracker.type=gitlab pero STACKY_GITLAB_ENABLED=false")

    monkeypatch.setattr(tp, "get_tracker_provider", _explota)
    comentarios, stats = fetch_comentarios_normalizados(project_name="GITLABTEST", item_id=1)
    assert comentarios == []
    assert len(stats["errors"]) == 1
    assert stats["errors"][0].startswith("tracker_provider_unavailable:")
    assert "azure devops" not in stats["errors"][0].lower()      # y NUNCA lo contrario


def test_un_fallo_de_red_del_provider_no_levanta(monkeypatch):
    import services.tracker_provider as tp
    from services.tracker_context import fetch_comentarios_normalizados

    class _Rompe:
        name = "gitlab"
        def fetch_comments(self, item_id):
            raise tp.TrackerApiError(503, "gateway timeout", kind="transient")

    monkeypatch.setattr(tp, "get_tracker_provider", lambda project=None: _Rompe())
    comentarios, stats = fetch_comentarios_normalizados(project_name="GITLABTEST", item_id=1)
    assert comentarios == []
    assert stats["errors"][0].startswith("fetch_comments_failed:")


def test_un_provider_sin_fetch_comments_se_declara_no_se_rompe(monkeypatch):
    import services.tracker_provider as tp
    from services.tracker_context import fetch_comentarios_normalizados

    monkeypatch.setattr(tp, "get_tracker_provider", lambda project=None: object())
    comentarios, stats = fetch_comentarios_normalizados(project_name="GITLABTEST", item_id=1)
    assert comentarios == []
    assert stats["errors"][0].startswith("capability_missing:")


# -- F5 - armador compartido --------------------------------------------------

def test_el_armador_enmascara_un_token_de_gitlab():
    from services.ado_context import construir_bloques_de_comentarios

    comentarios = [{"author": "A", "date": "2026-01-01",
                    "text": "el token es glpat-AbCdEf1234567890xyz, probalo",
                    "is_html": False}]
    bloques, n = construir_bloques_de_comentarios(comentarios, titulo="X")
    assert n == 1
    contenido = bloques[0]["content"]
    assert "glpat-AbCdEf1234567890xyz" not in contenido
    assert "<posible-secreto-omitido>" in contenido
    assert "probalo" in contenido            # el resto del comentario sobrevive


def test_el_armador_enmascara_tambien_en_el_camino_ADO():
    """El endurecimiento es deliberado y vale para los dos trackers."""
    from services.ado_context import construir_bloques_de_comentarios

    comentarios = [{"author": "A", "date": "2026-01-01",
                    "text": "<p>usa ghp_ABCDEFGHIJKLMNOPQRSTUV para clonar</p>"}]  # sin is_html
    bloques, _ = construir_bloques_de_comentarios(comentarios, titulo="Comentarios ADO del ticket")
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUV" not in bloques[0]["content"]


def test_markdown_de_gitlab_no_pasa_por_el_limpiador_de_html():
    """is_html=False: `List<int>` no se puede perder. Es contexto tecnico."""
    from services.ado_context import construir_bloques_de_comentarios

    comentarios = [{"author": "A", "date": "2026-01-01",
                    "text": "revisar el metodo Get<List<int>>() del repositorio", "is_html": False}]
    bloques, _ = construir_bloques_de_comentarios(comentarios, titulo="X")
    assert "List<int>" in bloques[0]["content"]


def test_html_de_ado_sigue_pasando_por_el_limpiador():
    """Sin is_html (camino ADO): el HTML se limpia, byte-identico a hoy."""
    from services.ado_context import construir_bloques_de_comentarios

    comentarios = [{"author": "A", "date": "2026-01-01", "text": "<p>hola</p><p>chau</p>"}]
    bloques, _ = construir_bloques_de_comentarios(comentarios, titulo="X")
    assert "<p>" not in bloques[0]["content"]
    assert "hola" in bloques[0]["content"] and "chau" in bloques[0]["content"]


def test_el_titulo_es_el_que_se_le_pasa_y_el_id_NO_cambia():
    from services.ado_context import construir_bloques_de_comentarios

    bloques, _ = construir_bloques_de_comentarios(
        [{"author": "A", "date": "", "text": "x", "is_html": False}],
        titulo="Comentarios del ticket (GitLab)")
    assert bloques[0]["id"] == "ado-comments"        # NO se renombra: ver Decision 1
    assert bloques[0]["title"] == "Comentarios del ticket (GitLab)"


def test_comentario_que_queda_vacio_tras_limpiar_no_produce_linea():
    from services.ado_context import construir_bloques_de_comentarios

    bloques, n = construir_bloques_de_comentarios(
        [{"author": "A", "date": "", "text": "<p></p>"}], titulo="X")
    assert bloques == [] and n == 0


def test_sin_comentarios_no_hay_bloque():
    from services.ado_context import construir_bloques_de_comentarios

    assert construir_bloques_de_comentarios([], titulo="X") == ([], 0)


# -- [ADICION ARQUITECTO] 2 - el bloque declara su procedencia y su recorte ----

def test_el_bloque_lleva_sello_de_procedencia_y_de_recorte():
    """El sello es la UNICA declaracion que el agente ve aunque la metadata se pierda.

    Con recorte: dice cuantos de cuantos. Sin recorte: dice cuantos y el sentido.
    """
    from services.ado_context import construir_bloques_de_comentarios

    coms = [{"author": "A", "date": "2026-01-0%d" % (i + 1), "text": f"c{i}", "is_html": False}
            for i in range(3)]
    # El literal es EXACTAMENTE el que produce _bloques_por_proveedor en F6:
    #   f"GitLab · {n} de {total} comentarios (los mas recientes)" + ", del mas antiguo
    #   al mas reciente"
    # (el parentesis de "los mas recientes" cierra ANTES de la coma; el de afuera lo
    # pone el armador). Ver §11.2 del plan, que trae la cadena renderizada completa.
    bloques, _ = construir_bloques_de_comentarios(
        coms, titulo="Comentarios del ticket (GitLab)",
        sello="GitLab · 3 de 200 comentarios (los mas recientes), del mas antiguo al mas reciente",
    )
    contenido = bloques[0]["content"]
    assert contenido.startswith("_(GitLab · 3 de 200 comentarios")
    assert "del mas antiguo al mas reciente)_" in contenido
    assert "c0" in contenido and "c2" in contenido
    # SIN sello (camino ADO por defecto): el contenido es BYTE-IDENTICO al de hoy.
    sin, _ = construir_bloques_de_comentarios(coms, titulo="Comentarios ADO del ticket")
    assert not sin[0]["content"].startswith("_(")
    assert sin[0]["content"].startswith("**A** (2026-01-01):")


# -- F6.4 - contrato: enrich NO se come ninguna clave de stats -----------------

def test_enrich_propaga_TODAS_las_claves_que_produce_el_armador(monkeypatch):
    """Guard de CLASE: si manana alguien agrega una clave a stats y se olvida de la
    whitelist de enrich (:389-394), este test se pone rojo NOMBRANDO la clave.

    ANTI-FALSO-VERDE (obligatorio): el detector se calibra PRIMERO con una clave
    inventada, para probar que de verdad detecta la perdida.
    """
    from services import ado_context

    producidas = {
        "comments_count": 3, "attachments_count": 0, "attachments_text_inlined": 0,
        "errors": [], "comments_truncated": True, "comments_total_disponibles": 200,
        "attachments_skipped_reason": "provider_sin_descarga_de_adjuntos",
        "_clave_centinela_inventada": "x",
    }
    monkeypatch.setattr(
        ado_context, "build_ado_context_blocks",
        lambda *a, **k: ([], dict(producidas)),
    )
    _, stats = ado_context.enrich(
        ticket_id=1, agent_type="technical", existing_blocks=[], ado_id=1,
        return_stats=True,
    )
    # (a) calibracion: la centinela SI se pierde => el detector funciona.
    assert "_clave_centinela_inventada" not in stats, (
        "enrich dejo de filtrar: este test ya no prueba nada, reescribilo"
    )
    # (b) contrato: las 3 claves del camino por proveedor SI llegan.
    perdidas = {k for k in (
        "comments_truncated", "comments_total_disponibles", "attachments_skipped_reason",
    ) if k not in stats}
    assert not perdidas, (
        f"enrich se comio {sorted(perdidas)}: agregalas al bucle de :395 (Plan 289 F6.3). "
        f"El dato existe en build_stats y NUNCA llega a metadata['ado_context']."
    )


def test_enrich_no_inventa_esas_claves_en_el_camino_ADO(monkeypatch):
    """P1: con un productor que NO las emite, el metadata queda byte-identico a hoy."""
    from services import ado_context

    monkeypatch.setattr(
        ado_context, "build_ado_context_blocks",
        lambda *a, **k: ([], {"comments_count": 2, "attachments_count": 0,
                              "attachments_text_inlined": 0, "errors": []}),
    )
    _, stats = ado_context.enrich(
        ticket_id=1, agent_type="technical", existing_blocks=[], ado_id=1,
        return_stats=True,
    )
    assert set(stats) == {"comments_count", "attachments_count", "attachments_text_inlined",
                          "skipped", "skipped_reason", "errors"}
    assert stats["comments_count"] == 2
