"""tests/test_plan277_write_path.py — Plan 277 F3. El write path escribe lo que el
read path sabe leer.

QUÉ PRUEBA ESTE ARCHIVO, en una línea: que cuando Stacky CREA un hijo en GitLab
escribe `type::<tipo>` normalizado y `epic::<iid>`, y que el enlace deja de fallar
en silencio.

CERO RED. Todo pasa por `_client._request` mockeado; el provider se construye
entero (no un objeto sintético) para que un request nuevo aparezca en el mock en
vez de esconderse.

Los asserts de AUSENCIA siembran primero el positivo (caso 4): "no hubo POST a
/links" también pasa cuando no hubo NINGUNA llamada, así que primero se verifica
que el PUT de la etiqueta SÍ ocurrió.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.tracker_provider import TrackerApiError, TrackerItem  # noqa: E402

_PROJ = "ripley/agenda-web"


def _provider(*, epics_native: bool = False, group: str = ""):
    """GitLabTrackerProvider real con el TRANSPORTE mockeado.

    Devuelve `(provider, cliente_mock)`. `cliente_mock._request` arranca devolviendo
    la tupla `(body, headers)` que el código real espera; cada test la reemplaza si
    necesita un cuerpo o una excepción distintos.
    """
    import config as config_module
    from services.gitlab_provider import GitLabTrackerProvider

    with patch("services.gitlab_provider.GitLabClient") as mock_cls, \
         patch.object(config_module.config, "GITLAB_URL", "https://gl.interno"), \
         patch.object(config_module.config, "GITLAB_PROJECT", _PROJ), \
         patch.object(config_module.config, "STACKY_GITLAB_GROUP", group), \
         patch.object(config_module.config, "STACKY_GITLAB_EPICS_NATIVE", epics_native):
        cliente = MagicMock()
        cliente._project_path.return_value = _PROJ
        cliente._request.return_value = ({"id": 900, "iid": 7, "labels": []}, {})
        mock_cls.return_value = cliente
        prov = GitLabTrackerProvider(project=_PROJ)
    return prov, cliente


def _llamadas(cliente) -> list[tuple[str, str, dict]]:
    """(verbo, path, json_body) de cada `_request`, sin importar cómo se pasaron."""
    salida = []
    for llamada in cliente._request.call_args_list:
        args, kwargs = llamada
        verbo = args[0] if args else kwargs.get("method", "")
        path = args[1] if len(args) > 1 else kwargs.get("path", "")
        salida.append((verbo, path, kwargs.get("json_body") or {}))
    return salida


# ── Caso 1: la etiqueta de tipo pasa por el contrato ─────────────────────────

def test_01_type_label_normaliza_el_espacio_que_rompia_el_parser():
    """`type::User Story` (crudo) no lo matcheaba `type::(\\w+)` del migrador y no
    coincidía con ningún token canónico: Stacky escribía algo que no sabía leer."""
    prov, _ = _provider()
    assert prov._type_label("User Story") == "type::user_story"
    # SEMBRADO: el caso que ya andaba tiene que seguir andando.
    assert prov._type_label("Epic") == "type::epic"


# ── Caso 2: create_item manda el label del contrato ──────────────────────────

def test_02_create_item_manda_type_epic_en_los_labels():
    prov, cliente = _provider()
    cliente._request.return_value = ({"id": 900, "iid": 7, "labels": ["type::epic"]}, {})

    prov.create_item(TrackerItem(item_type="Epic", title="Violeta Lugo",
                                 description_html="<p>d</p>"))

    verbo, path, body = _llamadas(cliente)[0]
    assert (verbo, path) == ("POST", f"/projects/{_PROJ}/issues")
    assert "type::epic" in body["labels"].split(","), body


# ── Caso 3: el mecanismo nuevo, verificado por verbo Y por body ──────────────

def test_03_link_parent_en_ce_hace_put_con_add_labels_epic():
    prov, cliente = _provider(epics_native=False)

    prov._link_parent("7", "42")

    assert _llamadas(cliente) == [
        ("PUT", f"/projects/{_PROJ}/issues/7", {"add_labels": "epic::42"})
    ], _llamadas(cliente)


# ── Caso 4: los issue-links se retiraron DE VERDAD ──────────────────────────

def test_04_link_parent_no_hace_ningun_post_a_links():
    """Assert de ausencia CON el positivo sembrado en el MISMO test: sin la primera
    aserción, "no hubo POST a /links" también pasaría con cero llamadas."""
    prov, cliente = _provider(epics_native=False)

    prov._link_parent("7", "42")

    hechas = _llamadas(cliente)
    # POSITIVO PRIMERO: el mecanismo nuevo corrió.
    assert any(v == "PUT" and p.endswith("/issues/7") for v, p, _ in hechas), hechas
    # Y recién ahí la ausencia significa algo.
    assert [c for c in hechas if c[1].endswith("/links")] == [], hechas
    assert [c for c in hechas if c[0] == "POST"] == [], hechas
    # El fallback también se borró del FUENTE, no solo de este camino.
    # Se mide por AST y SIN el docstring: el docstring de `_link_parent` EXPLICA por
    # qué se retiraron los issue-links, así que un `grep "/links"` sobre el texto
    # crudo daría rojo justo por documentar el arreglo (el gate chocaría con su
    # propio comentario). `ast.unparse` deja solo código: sin comentarios, sin doc.
    import ast

    fuente = (_BACKEND / "services" / "gitlab_provider.py").read_text(encoding="utf-8")
    fn = next(
        n for n in ast.walk(ast.parse(fuente))
        if isinstance(n, ast.FunctionDef) and n.name == "_link_parent"
    )
    sin_doc = [
        n for n in fn.body
        if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)
                and isinstance(n.value.value, str))
    ]
    codigo = "\n".join(ast.unparse(n) for n in sin_doc)
    # SEMBRADO: el extractor de verdad extrajo algo (una lista vacía pasaría todo).
    assert "add_labels" in codigo, f"el AST no capturó el cuerpo de _link_parent: {codigo!r}"
    assert "/links" not in codigo, "quedó viva la escritura de issue-links"
    mudos = [
        h for h in ast.walk(fn)
        if isinstance(h, ast.ExceptHandler) and all(isinstance(s, ast.Pass) for s in h.body)
    ]
    assert mudos == [], "quedó un `except ...: pass` dentro de _link_parent"


# ── Caso 5: el camino Premium se conserva ───────────────────────────────────

def test_05_con_epicas_nativas_usa_el_post_del_grupo_y_no_etiqueta():
    prov, cliente = _provider(epics_native=True, group="ripley")

    prov._link_parent("7", "42")

    hechas = _llamadas(cliente)
    assert hechas == [
        ("POST", "/groups/ripley/epics/42/issues", {"issue_id": "7"})
    ], hechas
    assert [c for c in hechas if c[0] == "PUT"] == [], (
        "el camino Premium etiquetó igual: se estarían escribiendo las dos cosas"
    )


# ── Caso 6: el 403 degrada a etiqueta y lo dice ─────────────────────────────

def test_06_el_403_de_epicas_nativas_degrada_a_etiqueta_y_loguea_info(caplog):
    prov, cliente = _provider(epics_native=True, group="ripley")

    def _responder(verbo, path, **kw):
        if verbo == "POST" and "/epics/" in path:
            raise TrackerApiError(403, "Forbidden")
        return ({"id": 900, "iid": 7}, {})

    cliente._request.side_effect = _responder

    with caplog.at_level(logging.INFO, logger="services.gitlab_provider"):
        prov._link_parent("7", "42")

    hechas = _llamadas(cliente)
    assert ("PUT", f"/projects/{_PROJ}/issues/7", {"add_labels": "epic::42"}) in hechas, hechas
    mensajes = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert any("403" in m and "epic::" in m for m in mensajes), mensajes


# ── Caso 7: solo el 403 significa "sin licencia" ────────────────────────────

def test_07_un_500_de_epicas_nativas_se_relanza_y_no_degrada():
    prov, cliente = _provider(epics_native=True, group="ripley")

    def _responder(verbo, path, **kw):
        if verbo == "POST" and "/epics/" in path:
            raise TrackerApiError(500, "Internal Server Error")
        return ({"id": 900, "iid": 7}, {})

    cliente._request.side_effect = _responder

    with pytest.raises(TrackerApiError) as exc:
        prov._link_parent("7", "42")
    assert exc.value.status == 500
    assert [c for c in _llamadas(cliente) if c[0] == "PUT"] == [], (
        "un 500 se disfrazó de Community Edition y etiquetó igual"
    )


# ── Caso 8: el fin del `except Exception: pass`, sin romper el flujo ────────

def test_08_si_el_put_falla_create_item_devuelve_parent_link_error_y_no_levanta(caplog):
    prov, cliente = _provider(epics_native=False)

    def _responder(verbo, path, **kw):
        if verbo == "POST" and path.endswith("/issues"):
            return ({"id": 900, "iid": 7, "labels": ["type::funcional"]}, {})
        if verbo == "PUT":
            raise TrackerApiError(404, "Not Found")
        return ({}, {})

    cliente._request.side_effect = _responder

    with caplog.at_level(logging.ERROR, logger="services.gitlab_provider"):
        resultado = prov.create_item(
            TrackerItem(item_type="Funcional", title="Hijo",
                        description_html="<p>d</p>", parent_id="42")
        )

    # El issue YA existe: se devuelve creado…
    assert resultado["iid"] == "7"
    # …pero el fallo es VISIBLE (antes era `pass` mudo).
    assert "parent_link_error" in resultado, resultado
    assert "42" in resultado["parent_link_error"], resultado["parent_link_error"]
    assert any("sin enlace de padre" in r.getMessage() for r in caplog.records), (
        [r.getMessage() for r in caplog.records]
    )
    # SEMBRADO: sin padre no aparece la clave, o el assert de arriba no distingue
    # "falló el enlace" de "esta clave está siempre".
    cliente._request.side_effect = None
    cliente._request.return_value = ({"id": 901, "iid": 8, "labels": []}, {})
    sin_padre = prov.create_item(
        TrackerItem(item_type="Funcional", title="Suelto", description_html="<p>d</p>")
    )
    assert "parent_link_error" not in sin_padre, sin_padre


# ── Caso 9: no se escribe basura en GitLab ──────────────────────────────────

def test_09_un_parent_id_no_numerico_avisa_y_no_hace_request(caplog):
    prov, cliente = _provider(epics_native=False)

    with caplog.at_level(logging.WARNING, logger="services.gitlab_provider"):
        prov._link_parent("7", "no-es-un-iid")

    assert _llamadas(cliente) == [], (
        "se mandó un request con un parent_id inválido: eso crea una etiqueta basura"
    )
    mensajes = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("no-es-un-iid" in m for m in mensajes), mensajes
    # SEMBRADO: con un iid VÁLIDO el mismo camino sí hace el request. Sin esto,
    # "cero llamadas" pasaría también con el provider roto.
    prov._link_parent("7", "42")
    assert len(_llamadas(cliente)) == 1, _llamadas(cliente)
