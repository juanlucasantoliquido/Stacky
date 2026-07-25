"""services/provider_capabilities.py -- Plan 218 F2.

Registro de capacidades por proveedor. PURO (sin I/O de red, sin DB, sin importar
adaptadores). Es la Capa 3 de la doctrina de normalización (§3.1 del plan): la tabla
machine-readable de QUÉ soporta cada proveedor y con QUÉ pérdida.

Regla de oro: una capacidad `absent` NUNCA se descubre por excepción en runtime.
Se consulta ANTES con supports() y se degrada con CapabilityUnavailable.

Este módulo nombra a los DOS proveedores por definición (son las claves de la
matriz): por eso está en NEUTRAL_REGISTRY_ALLOWLIST del censo de F1.
"""
from __future__ import annotations

# CONGELADO por el Plan 218 (§3.1). Agregar claves es aditivo; renombrar NO.
CAPABILITY_KEYS: tuple[str, ...] = (
    # tracker
    "tracker.items.list", "tracker.items.get", "tracker.items.create",
    "tracker.items.update_state", "tracker.items.update_assignee", "tracker.items.url",
    "tracker.states.list", "tracker.types.list", "tracker.query.search",
    "tracker.comments.list", "tracker.comments.list_all", "tracker.comments.post",
    "tracker.comments.idempotent",
    "tracker.attachments.list", "tracker.attachments.upload", "tracker.attachments.link",
    "tracker.hierarchy.link_parent", "tracker.hierarchy.find_child",
    "tracker.updates.history", "tracker.sync.full", "tracker.sync.incremental",
    "tracker.epics.list", "tracker.epics.create_native",
    "tracker.iterations.list", "tracker.milestones.list", "tracker.labels.ensure",
    # transporte del tracker: transversales, no métodos del puerto, pero sí
    # comportamiento que el contrato de F3 exige y que hoy diverge entre proveedores.
    "tracker.rate_limit.clamp", "tracker.auth.html_redirect",
    # repo
    "repo.file.read", "repo.file.commit", "repo.branch.list", "repo.branch.create",
    "repo.commit.list", "repo.tag.create",
    # merge request / pull request
    "mr.create", "mr.get", "mr.list", "mr.diff", "mr.comment", "mr.close",
    "mr.merge", "mr.approve", "mr.reviewers", "mr.policies",
    # ci
    "ci.pipeline.infer", "ci.pipeline.trigger", "ci.pipeline.monitor",
    "ci.pipeline.definition.find", "ci.pipeline.definition.ensure",
    "ci.jobs.failed", "ci.job.log", "ci.variables.list", "ci.variables.set",
    "ci.variables.delete", "ci.variables.masked", "ci.artifacts.list",
    "ci.artifacts.download", "ci.environments.list", "ci.approvals",
    # identidad y grupos (SOLO lectura del propio token — P9, nunca RBAC)
    "identity.me", "identity.user.find", "identity.members.list", "identity.groups.list",
    "identity.token.scopes",
    # eventos
    "events.webhook.inbound", "events.webhook.verify",
    # deep links
    "links.item", "links.mr", "links.commit", "links.pipeline", "links.epic",
)

CAPABILITY_STATUSES: tuple[str, ...] = ("full", "partial", "absent", "n/a")

# Mapa capacidad -> método del puerto TrackerProvider. Solo cubre el dominio
# `tracker.*` que TIENE método de puerto; lo usa test_matriz_no_miente_estructuralmente.
_CAPABILITY_TO_PORT_METHOD: dict[str, str] = {
    "tracker.items.list": "fetch_open_items",
    "tracker.items.get": "get_item",
    "tracker.items.create": "create_item",
    "tracker.items.update_state": "update_item_state",
    "tracker.items.update_assignee": "update_item_assignee",
    "tracker.items.url": "item_url",
    "tracker.states.list": "fetch_states",
    "tracker.comments.list": "fetch_comments",
    "tracker.comments.list_all": "fetch_all_comments",
    "tracker.comments.post": "post_comment",
    "tracker.comments.idempotent": "comment_exists",
    "tracker.attachments.list": "fetch_attachments",
    "tracker.attachments.upload": "upload_attachment",
    "tracker.attachments.link": "link_attachment",
    "tracker.hierarchy.find_child": "find_child_by_marker",
    "tracker.updates.history": "fetch_item_updates",
    "identity.me": "get_authenticated_user",
}


def _f(evidence: str) -> dict:
    return {"status": "full", "evidence": evidence, "loss": ""}


def _p(evidence: str, loss: str) -> dict:
    return {"status": "partial", "evidence": evidence, "loss": loss}


def _a(evidence: str = "") -> dict:
    return {"status": "absent", "evidence": evidence, "loss": ""}


def _na(evidence: str = "") -> dict:
    return {"status": "n/a", "evidence": evidence, "loss": ""}


# status + nota de pérdida OBLIGATORIA cuando status == "partial".
# Carga inicial verificada contra el código el 2026-07-25 (§6 del plan).
CAPABILITY_MATRIX: dict[str, dict[str, dict]] = {
    "azure_devops": {
        "tracker.items.list": _f("services/ado_client.py:319"),
        # Degradado de `full` a `partial` por el contrato conductual de F3 (2026-07-25):
        # el adaptador propaga AdoApiError crudo, que NO es de la jerarquía del puerto.
        "tracker.items.get": _p(
            "services/ado_provider.py:66",
            "propaga AdoApiError crudo en vez de TrackerApiError(kind='not_found'): "
            "el consumidor no puede distinguir 'no existe' de 'se cayó la API'",
        ),
        "tracker.items.create": _f("services/ado_provider.py:101"),
        "tracker.items.update_state": _f("services/ado_provider.py:81"),
        "tracker.items.update_assignee": _f("services/ado_provider.py:120"),
        "tracker.items.url": _f("services/ado_provider.py:69"),
        "tracker.states.list": _f("services/ado_client.py:393"),
        "tracker.types.list": _f("services/ado_client.py:416"),
        "tracker.query.search": _f("services/ado_client.py:325"),
        "tracker.comments.list": _f("services/ado_client.py:431"),
        "tracker.comments.list_all": _f("services/ado_client.py:796"),
        "tracker.comments.post": _f("services/ado_client.py:768"),
        "tracker.comments.idempotent": _f("services/ado_provider.py:95"),
        "tracker.attachments.list": _f("services/ado_client.py:458"),
        "tracker.attachments.upload": _f("services/ado_client.py:687"),
        "tracker.attachments.link": _f("services/ado_client.py:736"),
        "tracker.hierarchy.link_parent": _f("services/ado_provider.py:101"),
        "tracker.hierarchy.find_child": _f("services/ado_provider.py:115"),
        "tracker.updates.history": _f("services/ado_provider.py:137"),
        "tracker.sync.full": _f("services/ado_sync.py:102"),
        "tracker.sync.incremental": _p(
            "services/ado_sync.py:235",
            "upsert_single_work_item procesa de a un ítem: no hay ventana incremental "
            "por fecha ni cursor persistido",
        ),
        "tracker.epics.list": _f("services/ado_provider.py:487"),
        "tracker.epics.create_native": _f("services/ado_provider.py:101"),
        "tracker.iterations.list": _f("services/pm/ado_pm_collector.py:36"),
        "tracker.milestones.list": _a(),
        "tracker.labels.ensure": _a(),
        "tracker.rate_limit.clamp": _f("services/ado_client.py:49"),
        "tracker.auth.html_redirect": _f("services/ado_client.py:88"),
        "repo.file.read": _a(),
        "repo.file.commit": _f("services/ado_provider.py:146"),
        "repo.branch.list": _a(),
        "repo.branch.create": _a(),
        "repo.commit.list": _a(),
        "repo.tag.create": _a(),
        "mr.create": _f("services/ado_provider.py:265"),
        "mr.get": _f("services/ado_provider.py:301"),
        "mr.list": _f("services/ado_provider.py:405"),
        "mr.diff": _p(
            "services/ado_provider.py:429",
            "devuelve diff_available=False y diff_text vacío: el operador abre la PR "
            "en el navegador para ver el diff",
        ),
        "mr.comment": _f("services/ado_provider.py:460"),
        "mr.close": _f("services/ado_provider.py:469"),
        "mr.merge": _f("services/ado_provider.py:362"),
        "mr.approve": _a("services/ado_provider.py:476"),
        "mr.reviewers": _a(),
        "mr.policies": _a(),
        "ci.pipeline.infer": _p(
            "services/ado_ci_provider.py:20",
            "la inferencia es por LLM (ado_pipeline_inference), no lee pipelines reales: "
            "misma firma, semántica distinta a la de GitLab",
        ),
        "ci.pipeline.trigger": _f("services/ado_ci_provider.py:54"),
        "ci.pipeline.monitor": _f("services/ado_ci_provider.py:25"),
        "ci.pipeline.definition.find": _f("services/ado_pipeline_definitions.py:82"),
        "ci.pipeline.definition.ensure": _f("services/ado_pipeline_definitions.py:125"),
        "ci.jobs.failed": _f("services/ado_ci_logs.py:25"),
        "ci.job.log": _f("services/ado_ci_logs.py:49"),
        "ci.variables.list": _p(
            "services/ado_variables.py:25",
            "defecto abierto: AdoClient._request se liga SIN bind (ado_variables.py:14) "
            "y además exige una pipeline definition preexistente",
        ),
        "ci.variables.set": _p(
            "services/ado_variables.py:47",
            "defecto abierto: AdoClient._request se liga SIN bind (ado_variables.py:14)",
        ),
        "ci.variables.delete": _p(
            "services/ado_variables.py:88",
            "defecto abierto: AdoClient._request se liga SIN bind (ado_variables.py:14)",
        ),
        "ci.variables.masked": _a("services/ado_variables.py:44"),
        "ci.artifacts.list": _a(),
        "ci.artifacts.download": _a(),
        "ci.environments.list": _a(),
        "ci.approvals": _a(),
        "identity.me": _f("services/ado_identity.py:126"),
        "identity.user.find": _a(),
        "identity.members.list": _a(),
        "identity.groups.list": _a(),
        "identity.token.scopes": _a(),
        "events.webhook.inbound": _a("services/webhooks.py:123"),
        "events.webhook.verify": _a("services/webhooks.py:70"),
        "links.item": _p(
            "services/ado_provider.py:69",
            "ADO no tiene módulo de deep links: solo la URL del work item, compuesta a mano",
        ),
        "links.mr": _a(),
        "links.commit": _a(),
        "links.pipeline": _a(),
        "links.epic": _a(),
    },
    "gitlab": {
        "tracker.items.list": _f("services/gitlab_provider.py:155"),
        "tracker.items.get": _f("services/gitlab_provider.py:164"),
        "tracker.items.create": _f("services/gitlab_provider.py:252"),
        "tracker.items.update_state": _f("services/gitlab_provider.py:218"),
        "tracker.items.update_assignee": _p(
            "services/gitlab_provider.py:363",
            "si el usuario no resuelve, silencia el error y BORRA el asignado en vez de "
            "levantar un error tipado",
        ),
        "tracker.items.url": _p(
            "services/gitlab_provider.py:169",
            "devuelve None con los deep links apagados, violando la firma '-> str' del puerto",
        ),
        "tracker.states.list": _p(
            "services/gitlab_provider.py:84",
            "devuelve 4 claves lógicas hardcodeadas, no los estados reales del tracker "
            "ni los del perfil del cliente",
        ),
        "tracker.types.list": _a("services/gitlab_provider.py:45"),
        "tracker.query.search": _f("services/gitlab_provider.py:48"),
        "tracker.comments.list": _f("services/gitlab_provider.py:289"),
        "tracker.comments.list_all": _p(
            "services/gitlab_provider.py:293",
            "es idéntico a fetch_comments: no pagina el histórico completo ni acepta marker",
        ),
        "tracker.comments.post": _f("services/gitlab_provider.py:297"),
        "tracker.comments.idempotent": _f("services/gitlab_provider.py:307"),
        "tracker.attachments.list": _p(
            "services/gitlab_provider.py:343",
            "GitLab no tiene modelo de relaciones: los adjuntos se extraen por regex "
            "sobre la descripción del issue",
        ),
        "tracker.attachments.upload": _f("services/gitlab_provider.py:313"),
        "tracker.attachments.link": _f("services/gitlab_provider.py:325"),
        "tracker.hierarchy.link_parent": _p(
            "services/gitlab_provider.py:104",
            "sin licencia Premium no hay épicas nativas: cae a issue-links, que no son "
            "jerarquía real (no hay padre único)",
        ),
        "tracker.hierarchy.find_child": _p(
            "services/gitlab_provider.py:381",
            "devuelve el PADRE como proxy del hijo cuando no hay épica nativa",
        ),
        "tracker.updates.history": _p(
            "services/gitlab_provider.py:413",
            "las sub-consultas de resource_state_events / resource_label_events están "
            "silenciadas: sin historial de estado ni de etiquetas",
        ),
        "tracker.sync.full": _a("api/tickets.py:692"),
        "tracker.sync.incremental": _a(),
        "tracker.epics.list": _a(),
        "tracker.epics.create_native": _p(
            "services/gitlab_provider.py:104",
            "requiere licencia GitLab Premium; sin ella cae al fallback de issue-links",
        ),
        "tracker.iterations.list": _a(),
        "tracker.milestones.list": _p(
            "services/gitlab_provider.py:48",
            "solo se puede FILTRAR por milestone; no hay listado ni CRUD por el puerto",
        ),
        "tracker.labels.ensure": _p(
            "services/gitlab_provider.py:45",
            "las etiquetas type::* se envían al crear el ítem, pero no se garantiza que "
            "existan en el proyecto (GitLab las crea implícitas, sin color ni descripción)",
        ),
        "tracker.rate_limit.clamp": _p(
            "services/gitlab_client.py:146",
            "no clampea Retry-After: un valor hostil bloquea el hilo (ADO lo clampea a 30 s)",
        ),
        "tracker.auth.html_redirect": _p(
            "services/gitlab_client.py:164",
            "ante el HTML de login devuelve el texto crudo en vez de un error tipado de auth",
        ),
        "repo.file.read": _a("services/gitlab_provider.py:564"),
        "repo.file.commit": _f("services/gitlab_provider.py:592"),
        "repo.branch.list": _a(),
        "repo.branch.create": _a(),
        "repo.commit.list": _a(),
        "repo.tag.create": _a(),
        "mr.create": _f("services/gitlab_provider.py:626"),
        "mr.get": _f("services/gitlab_provider.py:651"),
        "mr.list": _f("services/gitlab_provider.py:705"),
        "mr.diff": _f("services/gitlab_provider.py:735"),
        "mr.comment": _f("services/gitlab_provider.py:764"),
        "mr.close": _f("services/gitlab_provider.py:772"),
        "mr.merge": _f("services/gitlab_provider.py:692"),
        "mr.approve": _f("services/gitlab_provider.py:779"),
        "mr.reviewers": _a(),
        "mr.policies": _a(),
        "ci.pipeline.infer": _f("services/gitlab_ci_provider.py:32"),
        "ci.pipeline.trigger": _f("services/gitlab_provider.py:524"),
        "ci.pipeline.monitor": _f("services/gitlab_provider.py:547"),
        "ci.pipeline.definition.find": _na("services/gitlab_provider.py:592"),
        "ci.pipeline.definition.ensure": _na("services/gitlab_provider.py:592"),
        "ci.jobs.failed": _f("services/gitlab_ci_logs.py:14"),
        "ci.job.log": _f("services/gitlab_ci_logs.py:27"),
        "ci.variables.list": _f("services/gitlab_variables.py:21"),
        "ci.variables.set": _f("services/gitlab_variables.py:46"),
        "ci.variables.delete": _f("services/gitlab_variables.py:112"),
        "ci.variables.masked": _f("services/gitlab_variables.py:46"),
        "ci.artifacts.list": _a(),
        "ci.artifacts.download": _a(),
        "ci.environments.list": _a(),
        "ci.approvals": _a(),
        "identity.me": _p(
            "services/gitlab_provider.py:146",
            "sin caché ni mapa de identidad por proyecto (ADO cachea en ado_user_map.json)",
        ),
        "identity.user.find": _a("services/gitlab_provider.py:94"),
        "identity.members.list": _a(),
        "identity.groups.list": _a(),
        "identity.token.scopes": _a(),
        "events.webhook.inbound": _a("services/webhooks.py:123"),
        "events.webhook.verify": _a("services/webhooks.py:70"),
        "links.item": _f("services/gitlab_deep_links.py:38"),
        "links.mr": _f("services/gitlab_deep_links.py:47"),
        "links.commit": _f("services/gitlab_deep_links.py:56"),
        "links.pipeline": _f("services/gitlab_deep_links.py:74"),
        "links.epic": _f("services/gitlab_deep_links.py:65"),
    },
}

_STATUS_LABEL = {
    "full": "completa",
    "partial": "parcial",
    "absent": "ausente",
    "n/a": "no aplica",
}


def _entry(provider: str, capability: str) -> dict:
    return CAPABILITY_MATRIX.get(provider, {}).get(capability) or {}


def capability_status(provider: str, capability: str) -> str:
    """Estado declarado. `absent` para lo desconocido (fail-closed consultivo)."""
    return _entry(provider, capability).get("status", "absent")


def supports(provider: str, capability: str) -> bool:
    """True solo si status es 'full' o 'partial'."""
    return capability_status(provider, capability) in ("full", "partial")


def capability_loss(provider: str, capability: str) -> str:
    """Texto de la pérdida declarada; '' si el status no es 'partial'."""
    entry = _entry(provider, capability)
    return entry.get("loss", "") if entry.get("status") == "partial" else ""


def _domain(capability: str) -> str:
    return capability.split(".", 1)[0]


def render_markdown_matrix() -> str:
    """Documento de paridad completo. PURA y DETERMINISTA (orden = CAPABILITY_KEYS)."""
    total = {p: {s: 0 for s in CAPABILITY_STATUSES} for p in CAPABILITY_MATRIX}
    for provider in CAPABILITY_MATRIX:
        for key in CAPABILITY_KEYS:
            total[provider][capability_status(provider, key)] += 1

    lineas = [
        "# Paridad Azure DevOps ↔ GitLab",
        "",
        "> **ARCHIVO GENERADO — no editar a mano.** Lo produce",
        "> `services.provider_capabilities.render_markdown_matrix()` y",
        "> `tests/test_plan218_capability_matrix.py::test_doc_de_paridad_esta_sincronizado`",
        "> queda ROJO si diverge. Fuente de verdad: `CAPABILITY_MATRIX` (Plan 218 F2).",
        "",
        "## Resumen",
        "",
        "| Proveedor | completa | parcial | ausente | no aplica |",
        "|---|---|---|---|---|",
    ]
    for provider in CAPABILITY_MATRIX:
        t = total[provider]
        lineas.append(
            f"| {provider} | {t['full']} | {t['partial']} | {t['absent']} | {t['n/a']} |"
        )

    lineas += [
        "",
        f"Total de capacidades declaradas: **{len(CAPABILITY_KEYS)}**.",
        "",
        "## Matriz por capacidad",
        "",
        "Una fila por capacidad: estado en cada proveedor, pérdida declarada cuando el",
        "estado es parcial, y la evidencia `archivo:línea` que lo respalda.",
        "",
        "| Capacidad | Azure DevOps | GitLab | Pérdida declarada | Evidencia ADO | Evidencia GitLab |",
        "|---|---|---|---|---|---|",
    ]

    dominio_actual = None
    for key in CAPABILITY_KEYS:
        dom = _domain(key)
        if dom != dominio_actual:
            dominio_actual = dom
            lineas.append(f"| **{dom}.\\*** | | | | | |")
        ado = capability_status("azure_devops", key)
        gl = capability_status("gitlab", key)
        perdidas = []
        for provider, etiqueta in (("azure_devops", "ADO"), ("gitlab", "GitLab")):
            loss = capability_loss(provider, key)
            if loss:
                perdidas.append(f"**{etiqueta}:** {loss}")
        ev_ado = _entry("azure_devops", key).get("evidence") or ""
        ev_gl = _entry("gitlab", key).get("evidence") or ""
        lineas.append(
            f"| `{key}` | {_STATUS_LABEL[ado]} | {_STATUS_LABEL[gl]} | "
            f"{' · '.join(perdidas) or '—'} | "
            f"{('`' + ev_ado + '`') if ev_ado else '—'} | "
            f"{('`' + ev_gl + '`') if ev_gl else '—'} |"
        )

    return "\n".join(lineas) + "\n"
