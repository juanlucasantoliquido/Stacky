"""Plan 291 F6/F7 — El guardia de "repo equivocado" y la paridad de los 3 runtimes.

F6 existe porque `_worktree_maps_to_wrong_repo` está construido y llamado desde
el plan 177, pero NUNCA se ejercitó contra un `origin` de GitLab. Es el guardia
contra el peor fallo posible de este eje (R1): commitear en el repositorio
equivocado. Antes de encender la creación de ramas, este guardia tiene que estar
probado.

F7 demuestra —EJECUTANDO, no grepeando— que el eje entra por la costura que los
3 runtimes comparten (`ticket_status.on_execution_end`).

⚠️ CERO RED, CERO DISCO DEL OPERADOR, CERO BASE. Ver el fixture `entorno`.
⚠️ PROHIBIDO llamar create_app(): con pytest en sys.modules y STACKY_TEST_MODE=1
   IGUAL arranca los watchers y hace efectos reales.
"""
from __future__ import annotations

import pytest

_HOST_TRACKER = "srvcgit01.imsolutions.local"
_ORIGIN_PROPIO = f"https://{_HOST_TRACKER}/grp/proj.git"
_ORIGIN_AJENO = "https://gitlab.com/otro/repo.git"


# ── Dobles del consumidor final ───────────────────────────────────────────────

class WriterFalso:
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
        self.marcas = []
        self.comentarios = []
        self.contenido = "def f():\n    return 1\n"
        self.origin = _ORIGIN_PROPIO

    def marca(self, status):
        for kw in self.marcas:
            if kw.get("status") == status:
                return kw
        return None


@pytest.fixture
def entorno(monkeypatch, tmp_path):
    """DUPLICADO A PROPÓSITO del fixture de tests/test_plan291_autocommit_redaccion.py.

    NO se importa del otro archivo ni se sube a un conftest.py compartido: el
    ratchet corre cada archivo EN AISLAMIENTO y una dependencia cruzada entre
    archivos de test rompería esa garantía. Son ~20 líneas; la duplicación es
    deliberada.
    """
    # (0) el intent store escribe en runtime_paths.data_dir() => backend/data.
    monkeypatch.setenv("STACKY_DATA_DIR", str(tmp_path / "data"))

    from services import incident_dev_pr
    from services import incident_dev_autocommit as ida
    import services.repo_writer
    import services.merge_request_provider

    e = _Entorno(tmp_path)

    monkeypatch.setattr(incident_dev_pr, "get_intent",
                        lambda eid: {"open_pr": True, "repo_root": str(tmp_path), "baseline": {}})
    monkeypatch.setattr(incident_dev_pr, "mark_intent",
                        lambda eid, **kw: e.marcas.append(kw))
    monkeypatch.setattr(incident_dev_pr, "snapshot_worktree", lambda root: {"entries": {}})
    monkeypatch.setattr(incident_dev_pr, "compute_changed_files",
                        lambda b, c: {"added_or_modified": ["src/a.py"], "deleted": []})
    monkeypatch.setattr(incident_dev_pr, "remote_origin_url", lambda root: e.origin)
    monkeypatch.setattr(ida, "_ticket_ado_id_and_project", lambda tid: (99, "RIPLEY"))
    monkeypatch.setattr(ida, "_read_text_or_none", lambda root, rel: e.contenido)
    monkeypatch.setattr(services.repo_writer, "get_repo_writer", lambda p: e.writer)
    monkeypatch.setattr(services.merge_request_provider, "get_merge_request_provider",
                        lambda p: e.mrp)
    monkeypatch.setattr(ida, "_comment_issue_safe", lambda *a, **k: e.comentarios.append(a))
    # F6 — el host del tracker se resuelve sin red.
    monkeypatch.setattr(ida, "_provider_host", lambda p: _HOST_TRACKER)
    return e


def _correr_hook_directo():
    from services.incident_dev_autocommit import maybe_open_pr_for_incident_dev
    maybe_open_pr_for_incident_dev(
        ticket_id=12, execution_id=34, final_status="completed", agent_type="incident_dev",
    )


# ══════════════════════════════════════════════════════════════════════════════
# F6 — el guardia de "repo equivocado", contra un origin de GitLab
# ══════════════════════════════════════════════════════════════════════════════

def _guardia(monkeypatch, origin, provider_host):
    from services import incident_dev_autocommit as ida
    monkeypatch.setattr(ida, "_provider_host", lambda p: provider_host)
    return ida._worktree_maps_to_wrong_repo(origin, "RIPLEY")


def test_f6_1_mismo_host_https_se_permite(monkeypatch):
    assert _guardia(monkeypatch, _ORIGIN_PROPIO, _HOST_TRACKER) is False


def test_f6_2_host_distinto_se_detiene(monkeypatch):
    assert _guardia(monkeypatch, _ORIGIN_AJENO, _HOST_TRACKER) is True


def test_f6_3_forma_ssh_scp_like_del_mismo_host_se_permite(monkeypatch):
    assert _guardia(monkeypatch, f"git@{_HOST_TRACKER}:grp/proj.git", _HOST_TRACKER) is False


def test_f6_4_forma_ssh_scp_like_de_otro_host_se_detiene(monkeypatch):
    assert _guardia(monkeypatch, "git@gitlab.com:otro/repo.git", _HOST_TRACKER) is True


def test_f6_5_la_comparacion_es_case_insensitive(monkeypatch):
    assert _guardia(monkeypatch, "https://SRVCGIT01.ImSolutions.LOCAL/g/p.git", _HOST_TRACKER) is False


def test_f6_6_si_el_host_del_tracker_no_resuelve_no_bloquea(monkeypatch):
    """Ante la duda → False. El guardia nunca degrada por debajo de v1."""
    assert _guardia(monkeypatch, _ORIGIN_AJENO, None) is False


def test_f6_7_a_origin_ajeno_detiene_el_commit(entorno):
    """F6.7 mitad que DETIENE — el gate real de la fase.

    Un test que solo mirara el booleano de _worktree_maps_to_wrong_repo sería un
    test estático sobre un defecto de ejecución. Este EJECUTA el post-hook y
    verifica que el writer no fue llamado.
    """
    entorno.origin = _ORIGIN_AJENO
    _correr_hook_directo()

    assert entorno.writer.llamadas == []
    assert entorno.mrp.llamadas == []
    saltado = entorno.marca("skipped")
    assert saltado is not None
    assert _ORIGIN_AJENO in saltado["error"]


def test_f6_7_b_origin_propio_deja_pasar_el_commit(entorno):
    """F6.7 mitad que GUARDA LA PRESENCIA — impide que la mitad de arriba pase
    porque el writer nunca se llama por otro motivo."""
    entorno.origin = _ORIGIN_PROPIO
    _correr_hook_directo()

    assert len(entorno.writer.llamadas) == 1
    assert len(entorno.mrp.llamadas) == 1


# ── F6.8 — K2, el gate REAL: la rama la construye EL PRODUCTO ────────────────

def _aserta_k2(entorno):
    """La aserción de K2, aislada para poder correrla en las DOS mitades."""
    _correr_hook_directo()
    assert entorno.writer.llamadas, "el writer no fue llamado"
    rama = entorno.writer.llamadas[0][2]
    assert rama == "stacky/incidencia-12-exec-34", rama


def test_f6_8_a_la_rama_del_auto_pr_la_construye_el_producto(entorno):
    """F6.8 — K2 acotado al auto-PR (§1.2).

    El F4.7 del v1 asertaba `branch.startswith("stacky/")` sobre ramas que el
    PROPIO TEST pasaba como argumento: un gate que comprueba su propio input y
    que no puede ponerse rojo nunca. Acá la rama sale de `_BRANCH_PREFIX` + los
    ids, dentro del producto.
    """
    _aserta_k2(entorno)


def test_f6_8_b_mitad_de_contraste_con_el_prefijo_parcheado(entorno, monkeypatch):
    """F6.8 — MITAD DE CONTRASTE OBLIGATORIA.

    Con el símbolo del producto parcheado, la MISMA aserción debe FALLAR. Sin
    esta segunda mitad, el gate no demuestra que puede ponerse rojo.
    """
    from services import incident_dev_autocommit as ida
    monkeypatch.setattr(ida, "_BRANCH_PREFIX", "suelto/")

    with pytest.raises(AssertionError):
        _aserta_k2(entorno)


# ══════════════════════════════════════════════════════════════════════════════
# F7 — Paridad de los 3 runtimes, probada EJECUTANDO el chokepoint
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def chokepoint(monkeypatch):
    """Registra el post-hook SIN llamar create_app().

    `monkeypatch.setattr(_POST_HOOKS, [])` antes de registrar deja la lista
    limpia y monkeypatch la restaura sola al terminar.

    `set_status` se neutraliza a propósito: es lo único de `on_execution_end`
    que toca la BASE. El chokepoint que esta fase prueba es `_run_post_hooks`,
    que sigue siendo el real y se ejecuta entero.
    """
    from services import ticket_status
    from services import incident_dev_autocommit as ida

    monkeypatch.setattr(ticket_status, "_POST_HOOKS", [])
    monkeypatch.setattr(ticket_status, "set_status", lambda *a, **k: None)
    ida.register(ticket_status.register_post_hook)
    return ticket_status


def test_f7_1_el_post_hook_queda_registrado(chokepoint):
    """F7.1 — DIAGNÓSTICO, casi vacuo por construcción (asserta que el fixture
    hizo lo que hizo). Se conserva solo para que, si F7.2 falla, se sepa si el
    problema es el registro o el disparo. EL GATE REAL ES F7.2."""
    from services.incident_dev_autocommit import maybe_open_pr_for_incident_dev

    assert maybe_open_pr_for_incident_dev in chokepoint._POST_HOOKS


def test_f7_2_el_chokepoint_compartido_dispara_el_auto_pr(entorno, chokepoint):
    """F7.2 — EL GATE. Se llama `on_execution_end` de verdad (keyword-only) y se
    comprueba que el efecto llegó al final de la cadena.

    Un test que grepeara los 3 runners buscando "on_execution_end" sería un test
    estático sobre un defecto de ejecución.
    """
    chokepoint.on_execution_end(
        ticket_id=12, execution_id=34, final_status="completed", agent_type="incident_dev",
    )

    assert len(entorno.writer.llamadas) == 1
    assert entorno.writer.llamadas[0][2] == "stacky/incidencia-12-exec-34"


def test_f7_3_otro_agente_no_dispara_el_auto_pr(entorno, chokepoint):
    """F7.3 — guarda la PRESENCIA del filtro para que F7.2 no pase por accidente."""
    chokepoint.on_execution_end(
        ticket_id=12, execution_id=34, final_status="completed", agent_type="incident",
    )

    assert entorno.writer.llamadas == []
