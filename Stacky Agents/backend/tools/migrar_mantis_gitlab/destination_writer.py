"""tools/migrar_mantis_gitlab/destination_writer.py — Plan 217 F4 (C1).

Único archivo del tool que importa `services.gitlab_provider`,
`services.gitlab_client` y `config` para el propósito de ESCRITURA — el
resto del núcleo (`migrator_mg_core.py`, futuro `migrator_mg_executor.py`)
habla solo contra la interfaz `DestinationWriter` definida acá, igual que
el origen habla contra `adapters.base.MantisReadAdapter`.

Cableado real verificado contra el código (corrección de la premisa v1
rechazada por C1 — ver changelog del plan):
  - `GitLabTrackerProvider.__init__` (`services/gitlab_provider.py:33-39`)
    lee `base_url = getattr(config, "GITLAB_URL", "")` y usa
    `project or getattr(config, "GITLAB_PROJECT", "")` — es decir, el
    `project` explícito por parámetro GANA sobre `config.GITLAB_PROJECT`
    si se pasa. Por eso alcanza con mutar `config.GITLAB_URL` y pasar
    `project=` explícito; mutar `config.GITLAB_PROJECT` es solo prolijidad
    de echo-back, no necesario funcionalmente.
  - `GitLabClient.__init__` (`services/gitlab_client.py:56,62`) resuelve
    `base_url` del PARÁMETRO recibido (o `os.getenv("GITLAB_URL")` como
    fallback) y el TOKEN vía `os.getenv("GITLAB_TOKEN")` en VIVO — nunca
    lee `config.GITLAB_TOKEN`. Por eso el token se inyecta vía
    `os.environ["GITLAB_TOKEN"]`, ANTES de instanciar el provider, no
    mutando el módulo `config`.

Gate anti-destino-equivocado (§8.1.8): `assert_target_matches` compara el
destino que el writer RESOLVIÓ REALMENTE (`effective_target()`, leído de
`self._provider._client._base_url`/`self._provider._project`, atributos
reales verificados en `gitlab_client.py:56` y `gitlab_provider.py:37`)
contra `destination.base_url`/`destination.project_path` del config.json —
blinda el fallo silencioso de que el provider haya resuelto un `config`
global viejo/vacío.
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

import config
from services.gitlab_provider import GitLabTrackerProvider
from services.tracker_provider import TrackerItem, TrackerQuery

_LOGGER_NAME = "migrar_mantis_gitlab.destination_writer"


class DestinationMismatchError(RuntimeError):
    """El destino que el writer resolvió realmente (`effective_target()`)
    NO coincide con `destination.base_url`/`destination.project_path` del
    `migration_config.json` (§8.1.8 del Plan 217, [ADICIÓN ARQUITECTO 1]).
    Nunca se ignora: escribir en el proyecto GitLab equivocado es
    irreversible en la práctica (§12 del plan: no hay "transacciones")."""


def _normalize_target(base_url: Optional[str], project_path: Optional[str]) -> tuple[str, str]:
    return (base_url or "").rstrip("/"), (project_path or "").strip("/")


def _normalize_assignee(value: Optional[str]) -> Optional[str]:
    """`mapping.user_map.map_user` puede devolver `"unassigned"` o
    `"assign_to:<user>"` (§4 del config) — el provider real espera un
    username GitLab plano o `None`."""
    if not value or value == "unassigned":
        return None
    if value.startswith("assign_to:"):
        return value.split(":", 1)[1]
    return value


# ── Interfaz abstracta ─────────────────────────────────────────────────────


class DestinationWriter(ABC):
    """Contrato mínimo de escritura contra el destino (GitLab), agnóstico
    de si es el provider real o un `DryRunGitLabWriter` (§10 del plan)."""

    @abstractmethod
    def create_item(self, payload: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def post_comment(self, item_iid: str, body: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def upload_attachment(self, file_path: str, filename: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def link_attachment(self, item_iid: str, attachment_meta: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def create_issue_link(self, source_iid: str, target_iid: str, link_type: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def fetch_states(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def fetch_open_items(self) -> list[dict]:
        """Devuelve TODOS los items del destino (abiertos Y cerrados) — F5
        (Plan 217 Batch 4) la usa para `hydrate_map_from_destination_mg`
        (rehidratación propia por marker). Sin parámetro `query`: este tool
        siempre quiere el universo completo, nunca un subconjunto filtrado."""
        raise NotImplementedError

    @abstractmethod
    def comment_exists(self, item_iid: str, marker: str) -> bool:
        """Idempotencia de comentarios (§11 del plan): antes de postear un
        comentario, F5 verifica si ya existe uno con este `marker`."""
        raise NotImplementedError

    @abstractmethod
    def effective_target(self) -> tuple[str, str]:
        """Devuelve `(base_url, project_path)` REALMENTE resueltos —
        insumo del gate anti-destino-equivocado (§8.1.8)."""
        raise NotImplementedError


# ── Implementación real (provider GitLab) ─────────────────────────────────


class GitLabDestinationWriter(DestinationWriter):
    """Único punto del tool que instancia `GitLabTrackerProvider` (C1)."""

    def __init__(self, destination_config, token: str) -> None:
        # 1. Token vía variable de entorno DEL PROCESO, ANTES de instanciar
        #    nada — GitLabClient lee os.getenv("GITLAB_TOKEN") en vivo en su
        #    __init__ (gitlab_client.py:62), nunca vía el módulo config.
        os.environ["GITLAB_TOKEN"] = token

        # 2. Destino EXPLÍCITO por parámetro. El Plan 218 F0/F4 amplió la
        #    firma del provider con `base_url=`/`group=` y corrigió sus
        #    lecturas para que vayan a `config.config` (la INSTANCIA) en vez
        #    del módulo. Mutar `config.GITLAB_URL` (el módulo) dejó de tener
        #    efecto: el provider resolvía base_url='' y el gate
        #    anti-destino-equivocado abortaba la corrida. Pasar el destino
        #    por parámetro es además más robusto que depender de cualquier
        #    global — no vuelve a romperse si el seam cambia otra vez.
        self._destination_config = destination_config
        # 3. Instanciar DIRECTO (no vía tracker_provider.get_tracker_provider,
        #    que exige STACKY_GITLAB_ENABLED).
        self._provider = GitLabTrackerProvider(
            project=destination_config.project_path,
            base_url=destination_config.base_url,
        )

    # ── DestinationWriter ───────────────────────────────────────────────

    def create_item(self, payload: dict) -> dict:
        known_top_level = {"title", "description", "labels", "assignee"}
        item = TrackerItem(
            item_type="issue",
            title=payload.get("title", ""),
            description_html=payload.get("description", ""),
            labels=tuple(payload.get("labels") or ()),
            assignee=_normalize_assignee(payload.get("assignee")),
            parent_id=payload.get("dest_parent_gitlab_iid"),
            # `milestone`/`state` (y cualquier otro campo del payload de
            # migrator_mg_core) no tienen slot dedicado en TrackerItem/
            # create_item (el provider real solo setea title/description/
            # labels/assignee/parent_id, gitlab_provider.py:250-274) — se
            # preservan en `fields` para que un batch posterior (F5/F6)
            # decida cómo aplicarlos (p. ej. update_item_state o un PUT de
            # milestone_id adicional). Gap documentado, no oculto.
            fields={k: v for k, v in payload.items() if k not in known_top_level},
        )
        return self._provider.create_item(item)

    def post_comment(self, item_iid: str, body: str) -> dict:
        return self._provider.post_comment(item_iid, body)

    def upload_attachment(self, file_path: str, filename: str) -> dict:
        return self._provider.upload_attachment(file_path, filename)

    def link_attachment(self, item_iid: str, attachment_meta: dict) -> dict:
        return self._provider.link_attachment(item_iid, attachment_meta)

    def create_issue_link(self, source_iid: str, target_iid: str, link_type: str) -> dict:
        """No existe un método público genérico de issue-links no-parent en
        `GitLabTrackerProvider` — solo `_link_parent` (privado,
        `gitlab_provider.py:102-128`), específico de jerarquía padre/hijo, y
        que además NO parametriza `link_type` (siempre usa la semántica
        default de la API). Para relaciones tipadas arbitrarias (relates_to/
        blocks/is_blocked_by, §5 del plan) se llama directo al cliente HTTP
        interno del provider (`self._provider._client`), replicando el
        patrón real ya usado por `_link_parent` (`POST
        /projects/:id/issues/:iid/links`, `gitlab_provider.py:122-126`) pero
        agregando `link_type`, que la API v4 de GitLab sí soporta."""
        proj_path = self._provider._client._project_path()
        body, _ = self._provider._client._request(
            "POST",
            f"/projects/{proj_path}/issues/{source_iid}/links",
            json_body={
                "target_project_id": self._provider._project,
                "target_issue_iid": target_iid,
                "link_type": link_type,
            },
        )
        return body if isinstance(body, dict) else {}

    def fetch_states(self) -> list[str]:
        # NOTA de imprecisión encontrada: la firma pedida originalmente era
        # `fetch_states(item_iid: str) -> dict`, pero el método REAL del
        # provider (`gitlab_provider.py:212`) es `fetch_states(self) ->
        # list[str]` (sin item_iid — devuelve los estados LÓGICOS del state
        # map, no el estado de un item puntual). Se implementa fiel al
        # provider real, no a la firma propuesta.
        return self._provider.fetch_states()

    def fetch_open_items(self) -> list[dict]:
        # `GitLabTrackerProvider._query_to_gitlab_params` (gitlab_provider.py
        # :46-51) SOLO agrega el parámetro `state` cuando `query.state` es
        # literalmente "open" o "closed" — cualquier OTRO valor (p.ej.
        # "all") deja el request SIN filtro de estado, y la API v4 de
        # GitLab, sin `state`, devuelve TODOS los issues (abiertos y
        # cerrados). Por eso alcanza con UNA sola llamada —no hacen falta
        # las 2 llamadas (abiertos + cerrados) que contemplaba el batch
        # como plan B— porque `TrackerQuery.state` no está restringido a
        # "open"/"closed" (es un `str` plano, `tracker_provider.py:23`),
        # así que "all" simplemente cae al branch "sin filtro".
        return self._provider.fetch_open_items(TrackerQuery(state="all"))

    def comment_exists(self, item_iid: str, marker: str) -> bool:
        return self._provider.comment_exists(item_iid, marker)

    def effective_target(self) -> tuple[str, str]:
        return (self._provider._client._base_url, self._provider._project)


# ── Implementación dry-run (§10 del plan) ─────────────────────────────────


class DryRunGitLabWriter(DestinationWriter):
    """Simula toda escritura sin llamar nunca al provider/cliente real.
    Permite que `execute --dry-run` corra exactamente el mismo camino de
    código que `execute` real (§10 del plan). Cada operación simulada queda
    en `self.simulated_ops` para que tests/reporte verifiquen qué se habría
    hecho."""

    def __init__(self, destination_config) -> None:
        self._destination_config = destination_config
        self.simulated_ops: list[dict] = []
        self._counter = 0
        self._logger = logging.getLogger(_LOGGER_NAME)

    def _next_fake_id(self) -> str:
        self._counter += 1
        return f"dryrun-{self._counter}"

    def create_item(self, payload: dict) -> dict:
        fake_iid = self._next_fake_id()
        self._logger.info("[SIMULACRO] habría creado issue %s (title=%r)", fake_iid, payload.get("title"))
        self.simulated_ops.append({"op": "create_item", "payload": payload, "iid": fake_iid})
        return {"iid": fake_iid}

    def post_comment(self, item_iid: str, body: str) -> dict:
        fake_id = self._next_fake_id()
        self._logger.info("[SIMULACRO] habría comentado en issue %s", item_iid)
        self.simulated_ops.append({"op": "post_comment", "item_iid": item_iid, "body": body, "id": fake_id})
        return {"id": fake_id}

    def upload_attachment(self, file_path: str, filename: str) -> dict:
        fake_id = self._next_fake_id()
        self._logger.info("[SIMULACRO] habría subido adjunto %r", filename)
        self.simulated_ops.append(
            {"op": "upload_attachment", "file_path": file_path, "filename": filename, "id": fake_id}
        )
        return {"id": fake_id, "url": f"/dryrun/{fake_id}/{filename}"}

    def link_attachment(self, item_iid: str, attachment_meta: dict) -> dict:
        self._logger.info("[SIMULACRO] habría enlazado adjunto al issue %s", item_iid)
        self.simulated_ops.append(
            {"op": "link_attachment", "item_iid": item_iid, "attachment_meta": attachment_meta}
        )
        return {"iid": item_iid}

    def create_issue_link(self, source_iid: str, target_iid: str, link_type: str) -> dict:
        fake_id = self._next_fake_id()
        self._logger.info(
            "[SIMULACRO] habría creado link %s -> %s (%s)", source_iid, target_iid, link_type
        )
        self.simulated_ops.append(
            {
                "op": "create_issue_link",
                "source_iid": source_iid,
                "target_iid": target_iid,
                "link_type": link_type,
                "id": fake_id,
            }
        )
        return {"id": fake_id}

    def fetch_states(self) -> list[str]:
        return []

    def fetch_open_items(self) -> list[dict]:
        # Coherencia consigo mismo (decisión documentada, a criterio de
        # este batch): en vez de devolver `[]` fijo, refleja los
        # `create_item` ya simulados como "items" con `iid`+`description` —
        # así `hydrate_map_from_destination_mg` (F5) puede ejercitarse en
        # un dry-run end-to-end sin tocar GitLab real ni requerir un
        # segundo fake distinto solo para probar la rehidratación.
        return [
            {"iid": op["iid"], "description": (op.get("payload") or {}).get("description", "")}
            for op in self.simulated_ops
            if op.get("op") == "create_item"
        ]

    def comment_exists(self, item_iid: str, marker: str) -> bool:
        # Mismo criterio de coherencia que `fetch_open_items`: busca entre
        # los `post_comment` simulados en vez de devolver `False` fijo.
        return any(
            op.get("op") == "post_comment"
            and op.get("item_iid") == item_iid
            and marker in (op.get("body") or "")
            for op in self.simulated_ops
        )

    def effective_target(self) -> tuple[str, str]:
        return (
            getattr(self._destination_config, "base_url", "") or "",
            getattr(self._destination_config, "project_path", "") or "",
        )


# ── Gate anti-destino-equivocado (§8.1.8) ─────────────────────────────────


def assert_target_matches(writer: DestinationWriter, destination_config) -> None:
    """Aborta con `DestinationMismatchError` si el destino REALMENTE
    resuelto por `writer` no coincide con `destination.base_url`/
    `destination.project_path` del config.json (normalizando trailing
    slashes). Lo invoca el futuro CLI (`validate`/`execute`, F9) antes de
    cualquier escritura real."""
    resolved_base_url, resolved_project = writer.effective_target()
    expected_base_url = getattr(destination_config, "base_url", None)
    expected_project = getattr(destination_config, "project_path", None)

    if _normalize_target(resolved_base_url, resolved_project) != _normalize_target(
        expected_base_url, expected_project
    ):
        raise DestinationMismatchError(
            "Gate anti-destino-equivocado (Plan 217 §8.1.8): el destino efectivo "
            f"del writer (base_url={resolved_base_url!r}, project_path={resolved_project!r}) "
            "NO coincide con destination.base_url/project_path del config.json "
            f"(base_url={expected_base_url!r}, project_path={expected_project!r}). "
            "Abortando para evitar escribir en el proyecto GitLab equivocado."
        )


__all__ = [
    "DestinationMismatchError",
    "DestinationWriter",
    "DryRunGitLabWriter",
    "GitLabDestinationWriter",
    "assert_target_matches",
]
