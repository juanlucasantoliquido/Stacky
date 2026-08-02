"""Plan 291 F5 — El auto-PR AVISA si el arreglo trae un secreto, y solo lo TAPA
si el operador lo pide.

Dos mitades, dos flags, y el orden importa:
  · STACKY_AUTOCOMMIT_SECRET_SCAN_ENABLED (ON)  → solo MIRA. Archivo byte-idéntico.
  · STACKY_AUTOCOMMIT_REDACT_ENABLED      (OFF) → además REEMPLAZA. Excepción (B).

⚠️ CERO RED, CERO DISCO DEL OPERADOR, CERO BASE. `maybe_open_pr_for_incident_dev`
toca disco, base, git y red por SEIS lados: el fixture `entorno` los patchea a
los seis y además manda `STACKY_DATA_DIR` a tmp_path, porque
`incident_dev_pr.get_intent` resuelve su carpeta con `runtime_paths.data_dir()`,
que sin esa variable es `backend/data` — la carpeta VIVA del operador (R13).
"""
from __future__ import annotations

import pytest


# ── Dobles del consumidor final ───────────────────────────────────────────────

class WriterFalso:
    """Doble de RepoWriter. `llamadas` guarda los argumentos TAL CUAL llegaron:
    las aserciones de esta fase van sobre el `content` que recibió commit_file,
    NO sobre el retorno de _inspeccionar."""

    def __init__(self):
        self.llamadas = []

    def commit_file(self, path, content, branch, message):
        self.llamadas.append((path, content, branch, message))
        return {"sha": "abc", "branch": branch, "path": path, "web_url": "", "status": "create"}


class MrpFalso:
    def __init__(self):
        self.llamadas = []

    def create_merge_request(self, *, source_branch, target_branch, title, description):
        self.llamadas.append({
            "source_branch": source_branch, "target_branch": target_branch,
            "title": title, "description": description,
        })
        return {"id": "7", "web_url": "http://gl.local/mr/7", "state": "open"}


class _Entorno:
    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        self.writer = WriterFalso()
        self.mrp = MrpFalso()
        self.marcas = []        # kwargs de cada mark_intent
        self.comentarios = []   # args de cada _comment_issue_safe
        self.contenido = "def f():\n    return 1\n"
        self.origin = None

    def marca(self, status):
        for kw in self.marcas:
            if kw.get("status") == status:
                return kw
        return None

    @property
    def descripcion_del_mr(self):
        assert self.mrp.llamadas, "no se llegó a crear el MR"
        return self.mrp.llamadas[0]["description"]


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    """Los SEIS puntos de patch (+ el aislamiento de data_dir). Se DUPLICA en
    tests/test_plan291_guardia_repo.py a propósito: el ratchet corre cada archivo
    EN AISLAMIENTO y una dependencia cruzada entre archivos de test rompería esa
    garantía. No va a un conftest.py compartido."""
    # (0) el intent store escribe en runtime_paths.data_dir() => backend/data.
    #     SIN esto, el test contamina la carpeta VIVA del operador.
    monkeypatch.setenv("STACKY_DATA_DIR", str(tmp_path / "data"))

    from services import incident_dev_pr
    from services import incident_dev_autocommit as ida
    import services.repo_writer
    import services.merge_request_provider

    e = _Entorno(tmp_path)

    # (1) el intent
    monkeypatch.setattr(incident_dev_pr, "get_intent",
                        lambda eid: {"open_pr": True, "repo_root": str(tmp_path), "baseline": {}})
    monkeypatch.setattr(incident_dev_pr, "mark_intent",
                        lambda eid, **kw: e.marcas.append(kw))
    # (2) el snapshot de git (si no, corre `git status` de verdad)
    monkeypatch.setattr(incident_dev_pr, "snapshot_worktree", lambda root: {"entries": {}})
    monkeypatch.setattr(incident_dev_pr, "compute_changed_files",
                        lambda b, c: {"added_or_modified": ["src/a.py"], "deleted": []})
    monkeypatch.setattr(incident_dev_pr, "remote_origin_url", lambda root: e.origin)
    # (3) el Ticket en la base (si no, abre session_scope contra la DB)
    monkeypatch.setattr(ida, "_ticket_ado_id_and_project", lambda tid: (99, "RIPLEY"))
    # (4) el contenido del archivo
    monkeypatch.setattr(ida, "_read_text_or_none", lambda root, rel: e.contenido)
    # (5) el writer y el proveedor de MR — se importan LAZY dentro de la función,
    #     así que hay que parchear el MÓDULO DE ORIGEN.
    monkeypatch.setattr(services.repo_writer, "get_repo_writer", lambda p: e.writer)
    monkeypatch.setattr(services.merge_request_provider, "get_merge_request_provider",
                        lambda p: e.mrp)
    # (6) el comentario en la Issue (si no, sale a la red del tracker)
    monkeypatch.setattr(ida, "_comment_issue_safe", lambda *a, **k: e.comentarios.append(a))
    return e


def _correr(entorno):
    from services.incident_dev_autocommit import maybe_open_pr_for_incident_dev
    maybe_open_pr_for_incident_dev(
        ticket_id=12, execution_id=34, final_status="completed", agent_type="incident_dev",
    )
    # El post-hook se traga TODA excepción (K3/Plan 135). Si algo del fixture
    # falla, el síntoma sería un intent en "error" y aserciones crípticas: lo
    # sacamos a la luz acá.
    err = entorno.marca("error")
    assert err is None, f"el auto-PR falló: {err}"


_SECRETO = "TOKEN_GH = 'ghp_" + "a" * 24 + "'\n"

# El caso que hundía al v1: código LEGÍTIMO que redact_secrets destruye.
_CODIGO_LEGITIMO = (
    'password = cfg.get("db_password")\n'
    "secret = None\n"
    'api_key = os.getenv("X")\n'
    "# autor: juan@empresa.com\n"
)


# ══════════════════════════════════════════════════════════════════════════════
# F5
# ══════════════════════════════════════════════════════════════════════════════

def test_f5_1_inspeccionar_avisa_sin_tocar_el_texto():
    """F5.1 — con los defaults de fábrica devuelve el texto IDÉNTICO y True."""
    from services.incident_dev_autocommit import _inspeccionar

    texto = "clave: ghp_" + "a" * 22
    salida, hubo = _inspeccionar(texto)

    assert salida == texto
    assert hubo is True


def test_f5_2_con_defaults_el_archivo_se_commitea_byte_identico(entorno):
    """F5.2 — la aserción va sobre el `content` que RECIBIÓ commit_file, no sobre
    el retorno de _inspeccionar."""
    entorno.contenido = _SECRETO
    _correr(entorno)

    assert len(entorno.writer.llamadas) == 1
    assert entorno.writer.llamadas[0][1] == _SECRETO


def test_f5_3_el_archivo_sospechoso_llega_a_la_descripcion_del_mr(entorno):
    """F5.3 — sobre el kwarg real de create_merge_request, no sobre el retorno de
    _build_pr_body.

    Este es el caso que obliga a MOVER la llamada a _build_pr_body: hoy se hacía
    ANTES del bucle de commits, cuando la lista de sospechosos todavía no existe.
    """
    entorno.contenido = _SECRETO
    _correr(entorno)

    assert "src/a.py" in entorno.descripcion_del_mr
    assert "Revisá estos archivos antes de integrar" in entorno.descripcion_del_mr


def test_f5_4_con_el_tapado_encendido_el_secreto_se_reemplaza(entorno, monkeypatch):
    """F5.4 — solo con la flag (B) encendida el contenido difiere del original."""
    import config
    monkeypatch.setattr(config.config, "STACKY_AUTOCOMMIT_REDACT_ENABLED", True, raising=False)
    entorno.contenido = _SECRETO
    _correr(entorno)

    subido = entorno.writer.llamadas[0][1]
    assert "ghp_" not in subido
    assert "***REDACTED***" in subido
    assert "src/a.py" in entorno.descripcion_del_mr


def test_f5_5_codigo_legitimo_no_se_toca_ni_con_el_tapado_encendido(entorno, monkeypatch):
    """F5.5 — 🔴 EL GATE DEL BLOQUEANTE C1.

    `password = cfg.get("db_password")`, `secret = None`, `api_key = os.getenv("X")`
    y un email de atribución pasan por el camino con el tapado ENCENDIDO y tienen
    que salir BYTE-IDÉNTICOS. Si alguien vuelve a meter `redact_secrets` entero
    (que sanea DIFFS PARA UN MODELO, no archivos que se escriben), este test se
    pone rojo.
    """
    import config
    monkeypatch.setattr(config.config, "STACKY_AUTOCOMMIT_REDACT_ENABLED", True, raising=False)
    entorno.contenido = _CODIGO_LEGITIMO
    _correr(entorno)

    assert entorno.writer.llamadas[0][1] == _CODIGO_LEGITIMO
    assert entorno.marca("opened")["secret_scan_files"] == []
    assert "Revisá estos archivos antes de integrar" not in entorno.descripcion_del_mr


def test_f5_6_archivo_limpio_pasa_identico_y_sin_seccion_de_aviso(entorno):
    """F5.6 — NO-REGRESIÓN: guarda la PRESENCIA del camino de hoy."""
    entorno.contenido = "def f():\n    return 1\n"
    _correr(entorno)

    assert entorno.writer.llamadas[0][1] == "def f():\n    return 1\n"
    assert "Revisá estos archivos antes de integrar" not in entorno.descripcion_del_mr


def test_f5_7_con_las_dos_apagadas_el_camino_es_byte_identico(entorno, monkeypatch):
    """F5.7 — el apagado total es exactamente el comportamiento de hoy."""
    import config
    monkeypatch.setattr(config.config, "STACKY_AUTOCOMMIT_SECRET_SCAN_ENABLED", False, raising=False)
    monkeypatch.setattr(config.config, "STACKY_AUTOCOMMIT_REDACT_ENABLED", False, raising=False)
    entorno.contenido = _SECRETO
    _correr(entorno)

    assert entorno.writer.llamadas[0][1] == _SECRETO
    assert "Revisá estos archivos antes de integrar" not in entorno.descripcion_del_mr
    assert entorno.marca("opened")["secret_scan_files"] == []


def test_f5_8_el_intent_recibe_la_lista_de_sospechosos(entorno):
    """F5.8 — mark_intent(status='opened') trae secret_scan_files."""
    entorno.contenido = _SECRETO
    _correr(entorno)

    assert entorno.marca("opened")["secret_scan_files"] == ["src/a.py"]
