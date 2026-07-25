"""Contrato CONDUCTUAL del puerto TrackerProvider. Plan 218 F3.

El MISMO cuerpo de test corre contra los adaptadores REALES de los dos proveedores;
lo único falseado es el transporte HTTP (P4). Reemplaza la falsa "conformance"
estructural, que solo verificaba `hasattr`/`callable`.

Reglas por status (C4):
  * 'full'    -> ejecuta su escenario y EXIGE el comportamiento neutral.
  * 'partial' -> ejecuta su escenario; si está en KNOWN_GAPS corre esperando el fallo
                 (equivalente en proceso a xfail(strict=True): si PASA, es FALLO).
  * 'absent'  -> se verifica por la vía CONSULTIVA (`supports()` es False), no por una
                 excepción que ningún adaptador levanta.
  * 'n/a'     -> se saltea con motivo (no es un gap: el proveedor no tiene ese concepto).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable

from services.provider_capabilities import capability_status, supports

from .known_gaps import KNOWN_GAPS

_MARKER = "<!-- stacky-task:CONTRATO-218 -->"


class ContractViolation(AssertionError):
    """El adaptador no cumple el comportamiento neutral del puerto."""


@dataclass(frozen=True)
class Scenario:
    capability: str
    nombre: str
    preparar: Callable  # (fake, provider_name) -> None
    verificar: Callable  # (provider, fake, ctx) -> None


def _write_bodies(fake) -> list:
    return [
        c["body"] for c in fake.calls()
        if c["method"] in ("POST", "PUT", "PATCH") and c["body"] is not None
    ]


def _dump(body) -> str:
    try:
        return json.dumps(body, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(body)


# ── Escenarios (idénticos para los dos proveedores) ──────────────────────────

def _prep_create(fake, provider_name):
    if provider_name == "azure_devops":
        fake.expect("POST", "/_apis/wit/workitems/$", status=200,
                    body=fake.fixture("item_created"))
    else:
        fake.expect("POST", "/issues", status=200, body=fake.fixture("item_created"))


def _check_create(provider, fake, ctx):
    from services.tracker_provider import TrackerItem

    titulo = "Contrato 218 — ítem de prueba"
    result = provider.create_item(TrackerItem(
        item_type="task", title=titulo, description_html="<p>cuerpo</p>",
    ))
    if not isinstance(result, dict):
        raise ContractViolation("create_item debe devolver un dict")
    if not str(result.get("id") or "").strip():
        raise ContractViolation(f"create_item sin id utilizable: {result!r}")
    enviados = " ".join(_dump(b) for b in _write_bodies(fake))
    if titulo not in enviados:
        raise ContractViolation("el request de creación no llevó el título tal cual")


def _prep_get_missing(fake, provider_name):
    ruta = "/_apis/wit/workitems/999" if provider_name == "azure_devops" else "/issues/999"
    fake.expect("GET", ruta, status=404, body={"message": "not found"})


def _check_get_missing(provider, fake, ctx):
    from services.tracker_provider import TrackerApiError

    try:
        provider.get_item("999")
    except TrackerApiError as exc:
        if getattr(exc, "kind", None) != "not_found":
            raise ContractViolation(f"kind esperado 'not_found', llegó {exc.kind!r}") from exc
        return
    except Exception as exc:  # noqa: BLE001
        raise ContractViolation(
            f"un ítem inexistente debe levantar TrackerApiError(kind='not_found'), "
            f"no {type(exc).__name__}: {exc}"
        ) from exc
    raise ContractViolation("un ítem inexistente no puede resolverse sin error")


def _prep_idempotencia(fake, provider_name):
    if provider_name == "azure_devops":
        fake.expect("POST", "/comments", status=200, body={"id": 1, "text": _MARKER})
        fake.expect("GET", "/comments", status=200, body={
            "comments": [{"text": f"<p>hecho {_MARKER}</p>",
                          "createdBy": {"displayName": "Agente"},
                          "createdDate": "2026-07-25T10:00:00Z"}],
        })
    else:
        fake.expect("POST", "/notes", status=200, body={"id": 1, "body": _MARKER})
        fake.expect("GET", "/notes", status=200, body=[
            {"id": 1, "body": f"hecho {_MARKER}", "system": False},
        ])


def _check_idempotencia(provider, fake, ctx):
    provider.post_comment("4242", f"<p>hecho {_MARKER}</p>")
    if not provider.comment_exists("4242", _MARKER):
        raise ContractViolation("comment_exists no reconoce el marcador recién posteado")
    if provider.comment_exists("4242", "<!-- marcador-que-no-existe -->"):
        raise ContractViolation("comment_exists dio verdadero para un marcador ausente")


def _paginas_de_comentarios(provider_name, total=120, por_pagina=60):
    if provider_name == "azure_devops":
        pagina = lambda base: {  # noqa: E731
            "comments": [
                {"text": f"<p>comentario {base + i}</p>",
                 "createdBy": {"displayName": "Agente"},
                 "createdDate": "2026-07-25T10:00:00Z"}
                for i in range(por_pagina)
            ],
        }
        p1 = pagina(0)
        p1["continuationToken"] = "pagina-2"
        return [p1, pagina(por_pagina)]
    return [
        [{"id": base + i, "body": f"comentario {base + i}", "system": False}
         for i in range(por_pagina)]
        for base in (0, por_pagina)
    ]


def _prep_paginado(fake, provider_name):
    p1, p2 = _paginas_de_comentarios(provider_name)
    if provider_name == "azure_devops":
        fake.expect("GET", "/comments", status=200, body=p1)
        fake.expect("GET", "/comments", status=200, body=p2)
    else:
        fake.expect("GET", "/notes", status=200, body=p1, headers={"X-Next-Page": "2"})
        fake.expect("GET", "/notes", status=200, body=p2, headers={"X-Next-Page": ""})


def _check_paginado(provider, fake, ctx):
    comentarios = provider.fetch_all_comments("4242")
    if len(comentarios) != 120:
        raise ContractViolation(
            f"fetch_all_comments debe recorrer TODAS las páginas: llegaron {len(comentarios)} de 120"
        )
    faltantes = [c for c in comentarios if not {"author", "date", "text"} <= set(c)]
    if faltantes:
        raise ContractViolation(
            "fetch_all_comments debe devolver la forma neutral {author,date,text}; "
            f"llegó {sorted(faltantes[0])}"
        )


def _prep_update_state(fake, provider_name):
    if provider_name == "azure_devops":
        fake.expect("PATCH", "/_apis/wit/workitems/4242", status=200,
                    body=fake.fixture("item_created"))
    else:
        fake.expect("GET", "/issues/4242", status=200, body={"labels": ["type::task"]})
        fake.expect("PUT", "/issues/4242", status=200, body=fake.fixture("item_created"))


def _check_update_state(provider, fake, ctx):
    result = provider.update_item_state("4242", "accepted")
    if not isinstance(result, dict):
        raise ContractViolation("update_item_state debe devolver un dict")
    enviados = " ".join(_dump(b) for b in _write_bodies(fake))
    if not enviados.strip():
        raise ContractViolation("update_item_state no envió ninguna escritura")
    if "accepted" not in enviados:
        raise ContractViolation(
            "la escritura debe llevar el estado del proveedor RESUELTO desde el estado "
            f"lógico 'accepted'; se envió: {enviados[:200]}"
        )


def _prep_assignee(fake, provider_name):
    if provider_name == "azure_devops":
        fake.expect("PATCH", "/_apis/wit/workitems/4242", status=200,
                    body=fake.fixture("item_created"))
    else:
        fake.expect("GET", "/users", status=200, body=[])
        fake.expect("PUT", "/issues/4242", status=200, body=fake.fixture("item_created"))


def _check_assignee(provider, fake, ctx):
    try:
        provider.update_item_assignee("4242", "usuario-inexistente")
    except Exception:  # noqa: BLE001 — fallar ruidosamente es comportamiento VÁLIDO acá
        return
    for body in _write_bodies(fake):
        if not isinstance(body, (dict, list)):
            continue
        texto = _dump(body)
        if "assignee" not in texto.lower():
            continue
        vacio = (
            (isinstance(body, dict) and body.get("assignee_ids") == [])
            or '"value": ""' in texto
            or '"value": null' in texto
        )
        if vacio:
            raise ContractViolation(
                "asignar a un usuario inexistente BORRÓ el asignado en silencio; "
                "el puerto exige error tipado o no-op, nunca pérdida de dato"
            )


def _prep_item_url(fake, provider_name):
    return None


def _check_item_url(provider, fake, ctx):
    import config as config_module

    original = getattr(config_module.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", True)
    try:
        for deep_links in (True, False):
            setattr(config_module.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", deep_links)
            url = provider.item_url("4242")
            if not isinstance(url, str) or not url.strip():
                raise ContractViolation(
                    "item_url declara '-> str' y debe devolver una URL no vacía SIEMPRE "
                    f"(con deep_links={deep_links} devolvió {url!r})"
                )
    finally:
        setattr(config_module.config, "STACKY_GITLAB_DEEP_LINKS_ENABLED", original)


def _prep_states(fake, provider_name):
    if provider_name == "azure_devops":
        fake.expect("GET", "/_apis/wit/workitemtypes", status=200, body={
            "value": [{"name": "Task", "states": [
                {"name": "New"}, {"name": "Active"}, {"name": "Technical Review"},
            ]}],
        })
    else:
        fake.expect("GET", "/labels", status=200, body=[
            {"name": "New"}, {"name": "Active"}, {"name": "Technical Review"},
        ])


def _check_states(provider, fake, ctx):
    estados = provider.fetch_states()
    if not fake.calls():
        raise ContractViolation(
            "fetch_states debe consultar al tracker: devolvió una lista sin hacer una "
            "sola llamada, o sea que está hardcodeada"
        )
    declarados = {"New", "Active", "Technical Review"}
    if not declarados <= set(estados):
        raise ContractViolation(
            f"fetch_states debe devolver los estados REALES del tracker; llegó {estados}"
        )


def _prep_find_child(fake, provider_name):
    if provider_name == "azure_devops":
        fake.expect("POST", "/_apis/wit/wiql", status=200, body={"workItems": [{"id": 777}]})
        fake.expect("GET", "/_apis/wit/workitems?ids=777", status=200, body={
            "value": [{"id": 777, "fields": {
                "System.Id": 777, "System.Title": "hija",
                "System.Description": f"<p>{_MARKER}</p>", "System.Parent": 100,
            }}],
        })
    else:
        fake.expect("GET", "/issues/100/links", status=200, body=[])
        fake.expect("GET", "/issues/100/notes", status=200, body=[
            {"id": 9, "body": f"la hija es la 777 {_MARKER}", "system": False},
        ])
        fake.expect("GET", "/issues/100", status=200, body={
            "id": 100, "iid": 100, "title": "padre", "web_url": "https://gl.test/i/100",
        })


def _check_find_child(provider, fake, ctx):
    hijo = provider.find_child_by_marker("100", _MARKER)
    if not hijo:
        raise ContractViolation("find_child_by_marker no encontró la hija marcada")
    ident = str(hijo.get("id") or hijo.get("iid") or "")
    if ident in ("100", ""):
        raise ContractViolation(
            f"find_child_by_marker devolvió el PADRE como proxy del hijo (id={ident!r})"
        )


def _prep_rate_limit(fake, provider_name):
    ruta = "/comments" if provider_name == "azure_devops" else "/notes"
    fake.expect("POST", ruta, status=429, body={"message": "slow down"},
                headers={"Retry-After": "99999"})
    fake.expect("POST", ruta, status=200,
                body={"id": 1, "text": "ok", "body": "ok"})


def _check_rate_limit(provider, fake, ctx):
    provider.post_comment("4242", "<p>hola</p>")
    esperas = ctx["sleeps"]
    if not esperas:
        raise ContractViolation("un 429 con Retry-After debe reintentar tras esperar")
    if max(esperas) > 30.0:
        raise ContractViolation(
            f"un Retry-After hostil debe clamparse (≤30 s): se durmió {max(esperas)} s"
        )


def _prep_html_login(fake, provider_name):
    html = "<html><head><title>Azure DevOps Services | Sign In</title></head></html>"
    if provider_name == "azure_devops":
        fake.expect("GET", "/_apis/wit/workitems/4242", status=200, body=html,
                    headers={"Content-Type": "text/html",
                             "X-Final-Url": "https://login.microsoftonline.com/_signin"})
    else:
        fake.expect("GET", "/issues/4242", status=200, body=html,
                    headers={"Content-Type": "text/html"})


def _check_html_login(provider, fake, ctx):
    try:
        resultado = provider.get_item("4242")
    except Exception as exc:  # noqa: BLE001
        texto = f"{type(exc).__name__}: {exc}".lower()
        tipado = (
            getattr(exc, "kind", None) == "auth"
            or getattr(exc, "status", None) in (401, 403)
            or getattr(exc, "status_code", None) in (401, 403)
            or "sign-in" in texto or "sign in" in texto or "auth" in texto
        )
        if not tipado:
            raise ContractViolation(
                "ante el HTML de login el puerto debe levantar un error TIPADO de auth, "
                f"no {type(exc).__name__}: {exc}"
            ) from exc
        return
    raise ContractViolation(
        f"el HTML de login se devolvió como si fuera un ítem válido: {str(resultado)[:120]}"
    )


SCENARIOS: tuple[Scenario, ...] = (
    Scenario("tracker.items.create", "create_item", _prep_create, _check_create),
    Scenario("tracker.items.get", "get_item inexistente", _prep_get_missing, _check_get_missing),
    Scenario("tracker.comments.idempotent", "post_comment + comment_exists",
             _prep_idempotencia, _check_idempotencia),
    Scenario("tracker.comments.list_all", "fetch_all_comments paginado (120)",
             _prep_paginado, _check_paginado),
    Scenario("tracker.items.update_state", "update_item_state", _prep_update_state,
             _check_update_state),
    Scenario("tracker.items.update_assignee", "update_item_assignee inexistente",
             _prep_assignee, _check_assignee),
    Scenario("tracker.items.url", "item_url siempre str", _prep_item_url, _check_item_url),
    Scenario("tracker.states.list", "fetch_states reales", _prep_states, _check_states),
    Scenario("tracker.hierarchy.find_child", "find_child_by_marker devuelve el hijo",
             _prep_find_child, _check_find_child),
    Scenario("tracker.rate_limit.clamp", "429 con Retry-After hostil", _prep_rate_limit,
             _check_rate_limit),
    Scenario("tracker.auth.html_redirect", "respuesta HTML de login", _prep_html_login,
             _check_html_login),
)


def run_tracker_contract(make_provider, provider_name: str, fake) -> list[str]:
    """Ejecuta el contrato conductual del puerto contra un provider REAL.

    Devuelve la lista de capacidades verificadas (claves de CAPABILITY_KEYS).

    KNOWN_GAPS ⇒ semántica de `xfail(strict=True)` implementada en proceso: el escenario
    corre igual, se ESPERA que falle, y si PASA se levanta un error (equivalente al XPASS)
    cuyo único remedio es borrar la entrada del registro.
    """
    verificadas: list[str] = []
    for esc in SCENARIOS:
        status = capability_status(provider_name, esc.capability)
        if status == "n/a":
            continue
        if status == "absent":
            if supports(provider_name, esc.capability):
                raise ContractViolation(
                    f"{provider_name}/{esc.capability}: declarado 'absent' pero supports() dice True"
                )
            continue

        gap = KNOWN_GAPS.get((provider_name, esc.capability))
        fake.reset()
        esc.preparar(fake, provider_name)
        ctx: dict = {"sleeps": []}
        provider = make_provider(ctx)

        try:
            esc.verificar(provider, fake, ctx)
        except Exception as exc:  # noqa: BLE001
            if gap is None:
                raise ContractViolation(
                    f"[{provider_name}] escenario '{esc.nombre}' "
                    f"({esc.capability}): {exc}"
                ) from exc
            verificadas.append(esc.capability)  # gap conocido y todavía roto: contrato honrado
            continue

        if gap is not None:
            raise ContractViolation(
                f"XPASS — [{provider_name}] '{esc.nombre}' ({esc.capability}) YA FUNCIONA, "
                f"pero sigue registrado en KNOWN_GAPS (dueño: plan {gap['owner_plan']}). "
                "Borrá la entrada de tests/contract/known_gaps.py y actualizá "
                "CAPABILITY_MATRIX en el mismo commit."
            )
        verificadas.append(esc.capability)

    return verificadas
