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


def habilitar_pin_de_certificado_hoja() -> bool:
    """Permite que un certificado NO auto-firmado presente en el bundle actúe
    como ancla de confianza (`X509_V_FLAG_PARTIAL_CHAIN`).

    POR QUÉ HACE FALTA: `srvcgit01.imsolutions.local` presenta SOLO su
    certificado hoja (cadena de 1 elemento, verificado en vivo: `chain.Build`
    de .NET devuelve `PartialChain`), y su emisora (`CN=imsolutions.local`,
    `O=PFSTechSL`) no está ni en el bundle ni en el almacén de Windows. Con
    la verificación por defecto, OpenSSL busca la emisora, no la encuentra y
    falla con `unable to get local issuer certificate` — que es exactamente
    lo que pasaba: `ca-bundle-migrador.pem` contiene la HOJA, no la CA, así
    que el bundle NO servía para verificar el destino.

    Esto NO debilita la verificación: la hoja pineada tiene que coincidir
    EXACTAMENTE con la que presenta el servidor (es pinning, más estricto
    que confiar en una CA que puede emitir para cualquier host), el
    `check_hostname` sigue activo, y un host cuyo certificado no esté en el
    bundle sigue siendo rechazado (verificado con un control negativo).

    Se parchea el punto de creación del contexto de urllib3 porque
    `services/gitlab_client.py` usa `requests.request(...)` a nivel módulo
    (no una `Session`), así que no hay dónde montar un `HTTPAdapter` propio
    sin tocar el cliente compartido. Se parchean AMBOS módulos: `urllib3.
    connection` importa el nombre por valor (`from .util.ssl_ import
    create_urllib3_context`), así que parchear solo `urllib3.util.ssl_` no
    tendría efecto sobre las conexiones reales.
    """
    import ssl as _ssl

    import urllib3.connection as _u3conn
    import urllib3.util.ssl_ as _u3ssl

    if getattr(_u3ssl, "_mg_partial_chain_patched", False):
        return False

    _original = _u3ssl.create_urllib3_context

    def _con_partial_chain(*args, **kwargs):
        ctx = _original(*args, **kwargs)
        try:
            ctx.verify_flags |= _ssl.VERIFY_X509_PARTIAL_CHAIN
        except (AttributeError, ValueError):
            # Python sin el flag: se deja el contexto tal cual (falla ruidosa
            # en el handshake, nunca una verificación silenciosamente laxa).
            pass
        return ctx

    _u3ssl.create_urllib3_context = _con_partial_chain
    _u3conn.create_urllib3_context = _con_partial_chain
    _u3ssl._mg_partial_chain_patched = True
    logging.getLogger(_LOGGER_NAME).info(
        "Verificación TLS con pin de certificado hoja habilitada "
        "(VERIFY_X509_PARTIAL_CHAIN); la verificación sigue activa."
    )
    return True


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
    def post_comment(self, item_iid: str, body: str, created_at: Optional[str] = None) -> dict:
        """`created_at` (ISO 8601) backdatea la nota. La API v4 lo acepta en
        `POST /issues/:iid/notes` con permisos de admin u owner del proyecto."""
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
    def ensure_milestone(self, title: str) -> Optional[int]:
        """Devuelve el `milestone_id` del milestone con ese título, creándolo si
        no existe. `None` si no se pudo resolver.

        Existe porque `field_mapping.version.target_version_as = "milestone"`
        prometía "Milestone GitLab (se crea si no existe)" y nada lo hacía: el
        `milestone` calculado por `migrator_mg_core` caía en el mismo `fields`
        inerte que el `state`. Medido en el proyecto 310: **17 tickets** traen
        `target_version`, así que el gap era real, no teórico."""
        raise NotImplementedError

    @abstractmethod
    def apply_item_state(
        self, item_iid: str, desired_state: str, updated_at: Optional[str] = None
    ) -> dict:
        """Cierra o reabre un issue del destino. `desired_state` ∈
        {`opened`, `closed`} — el vocabulario de `field_mapping.status.
        <X>.gitlab_state`, NO el `state_event` de la API (la traducción a
        `close`/`reopen` es responsabilidad de la implementación).

        Este método es la pieza que faltaba para que el `gitlab_state` que
        `migrator_mg_core._build_payload` calcula llegue efectivamente a
        GitLab: `create_item` no lo puede aplicar porque `TrackerItem`/
        `GitLabTrackerProvider.create_item` no tienen slot para el estado
        (`gitlab_provider.py:296-320` solo envía title/description/labels/
        assignee/parent). Ver `migrator_mg_states.py`."""
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

    def attachment_exists(self, item_iid: str, marker: str, filename: str = "") -> bool:
        """Idempotencia de ADJUNTOS. Deliberadamente NO abstracto: el default
        conservador es "no existe", que a lo sumo reintenta una subida; el
        default contrario (True) SALTEARÍA adjuntos que faltan de verdad, que
        es el fallo que se está corrigiendo. Las implementaciones que sí
        pueden mirar el destino lo sobreescriben."""
        return False

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

        # 1b. CA bundle del destino, ANTES de instanciar el provider.
        #
        # `services/gitlab_client.py` usa `requests` sin pasar `verify`, así que
        # contra una instancia con certificado interno/self-signed la corrida
        # muere con `SSLError: CERTIFICATE_VERIFY_FAILED` en la PRIMERA lectura
        # del destino. Pasó de verdad: la re-migración de Ripley abortó ahí,
        # después de haber borrado las 52 issues, dejando el proyecto vacío.
        # (`validate` no lo detecta porque `effective_target()` no toca la red.)
        #
        # `requests` respeta `REQUESTS_CA_BUNDLE` del entorno, así que alcanza
        # con exportarlo — sin tocar el cliente compartido. Se usa un BUNDLE y no
        # `verify=False` a propósito: verificar el certificado real es más seguro
        # que ignorar la verificación, y deja de funcionar si alguien intercepta
        # el tráfico, que es exactamente lo que uno quiere.
        ca_bundle = getattr(destination_config, "ca_bundle", "") or ""
        if ca_bundle:
            ruta = os.path.abspath(ca_bundle)
            if not os.path.isfile(ruta):
                raise FileNotFoundError(
                    f"destination.ca_bundle apunta a '{ca_bundle}' (resuelto a "
                    f"'{ruta}') y no existe. Sin el bundle, `requests` no puede "
                    "verificar el certificado del GitLab destino y la corrida "
                    "aborta en la primera lectura."
                )
            os.environ["REQUESTS_CA_BUNDLE"] = ruta
            logging.getLogger(_LOGGER_NAME).info(
                "REQUESTS_CA_BUNDLE apuntado a %s", ruta
            )
            # El bundle pinea la HOJA de srvcgit01 (su CA emisora no existe en
            # ningún almacén de esta máquina), y una hoja no auto-firmada no
            # sirve como ancla salvo con PARTIAL_CHAIN. Sin esto, TODA lectura
            # y escritura contra el GitLab destino muere con
            # `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`.
            habilitar_pin_de_certificado_hoja()

        # 2. Destino EXPLÍCITO por parámetro. El Plan 218 F0/F4 amplió la
        #    firma del provider con `base_url=`/`group=` y corrigió sus
        #    lecturas para que vayan a `config.config` (la INSTANCIA) en vez
        #    del módulo. Mutar `config.GITLAB_URL` (el módulo) dejó de tener
        #    efecto: el provider resolvía base_url='' y el gate
        #    anti-destino-equivocado abortaba la corrida. Pasar el destino
        #    por parámetro es además más robusto que depender de cualquier
        #    global — no vuelve a romperse si el seam cambia otra vez.
        self._destination_config = destination_config
        self._logger = logging.getLogger(_LOGGER_NAME)
        #  `{titulo: milestone_id | None}` — ver `ensure_milestone`.
        self._milestone_cache: "dict[str, Optional[int]]" = {}
        # 3. Instanciar DIRECTO (no vía tracker_provider.get_tracker_provider,
        #    que exige STACKY_GITLAB_ENABLED).
        self._provider = GitLabTrackerProvider(
            project=destination_config.project_path,
            base_url=destination_config.base_url,
        )

    # ── DestinationWriter ───────────────────────────────────────────────

    def create_item(self, payload: dict) -> dict:
        # Camino de FIDELIDAD DE FECHA: `created_at` sólo se puede setear en el
        # POST de creación (la API v4 NO lo acepta en el PUT), y
        # `GitLabTrackerProvider.create_item` (`gitlab_provider.py:296-320`) no
        # tiene forma de pasarlo: arma su `create_body` con title/description/
        # labels/assignee_ids y nada más. Por eso, cuando el payload trae
        # `created_at`, este writer hace el POST directo replicando ese mismo
        # body y agregando el campo, en vez de delegar.
        #
        # Requisito verificado contra ESTA instancia (GitLab 18.0.2 CE): el
        # schema GraphQL declara `CreateIssueInput.createdAt` como "Available
        # only for admins and project owners", y el token del operador es Owner
        # del proyecto 127 (`permissions.project_access.access_level = 50`).
        # Si la instancia lo rechazara, `create_item_con_fecha` degrada al
        # camino normal en vez de abortar la migración.
        # El camino directo se usa si hay QUE SETEAR algo que el provider no
        # sabe pasar: `created_at` (solo aceptado en el POST) o `milestone_id`.
        if payload.get("created_at") or payload.get("milestone"):
            return self._create_item_con_fecha(payload)
        return self._create_item_via_provider(payload)

    def _create_item_via_provider(self, payload: dict) -> dict:
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

    def ensure_milestone(self, title: str) -> Optional[int]:
        """`GET /projects/:id/milestones?title=` y, si no existe, `POST`.

        Se cachea por título: los 17 tickets con versión del proyecto 310 se
        agrupan en pocos milestones, y sin caché cada uno costaría un GET.
        """
        limpio = (title or "").strip()
        if not limpio:
            return None
        if limpio in self._milestone_cache:
            return self._milestone_cache[limpio]

        proj_path = self._provider._client._project_path()
        try:
            existentes, _ = self._provider._client._request(
                "GET",
                f"/projects/{proj_path}/milestones",
                params={"title": limpio},
            )
            if isinstance(existentes, list) and existentes:
                mid = int(existentes[0].get("id"))
                self._milestone_cache[limpio] = mid
                return mid

            creado, _ = self._provider._client._request(
                "POST", f"/projects/{proj_path}/milestones", json_body={"title": limpio}
            )
            mid = int((creado or {}).get("id"))
            self._milestone_cache[limpio] = mid
            self._logger.info("milestone creado: %r -> id=%s", limpio, mid)
            return mid
        except Exception as exc:
            # Un milestone no vale abortar la migración de un issue: se declara y
            # el issue se crea sin él (la versión igual queda en la metadata).
            self._logger.warning(
                "no se pudo resolver el milestone %r: %s. El issue se crea sin milestone.",
                limpio, exc,
            )
            self._milestone_cache[limpio] = None
            return None

    def _create_item_con_fecha(self, payload: dict) -> dict:
        """POST directo a `/issues` con `created_at`, replicando fielmente el
        body de `GitLabTrackerProvider.create_item:299-307` (incluido el label
        de tipo y la resolución del assignee por username, que se reusan del
        provider para no divergir de él).

        Si GitLab rechaza el `created_at` (403/400 por permisos insuficientes),
        se reintenta UNA vez por el camino normal: perder la fecha de creación es
        una degradación aceptable y declarada; perder el issue no lo es.
        """
        proj_path = self._provider._client._project_path()
        labels = list(payload.get("labels") or []) + [self._provider._type_label("issue")]
        create_body: dict = {
            "title": payload.get("title", ""),
            "description": payload.get("description", ""),
            "labels": ",".join(labels),
        }
        if payload.get("created_at"):
            create_body["created_at"] = payload["created_at"]
        if payload.get("milestone"):
            milestone_id = self.ensure_milestone(str(payload["milestone"]))
            if milestone_id:
                create_body["milestone_id"] = milestone_id
        assignee = _normalize_assignee(payload.get("assignee"))
        if assignee:
            assignee_id = self._provider._resolve_assignee_id(assignee)
            if assignee_id:
                create_body["assignee_ids"] = [assignee_id]

        try:
            body, _ = self._provider._client._request(
                "POST", f"/projects/{proj_path}/issues", json_body=create_body
            )
        except Exception as exc:
            self._logger.warning(
                "create_item: GitLab rechazó created_at=%r (%s). Se reintenta SIN "
                "backdating: la fecha real queda solo en el bloque de metadata de "
                "la descripción.",
                payload.get("created_at"), exc,
            )
            sin_fecha = {k: v for k, v in payload.items() if k != "created_at"}
            if sin_fecha.get("milestone"):
                # El provider tampoco sabe pasar el milestone: se reintenta el
                # POST directo sin `created_at` pero conservandolo.
                try:
                    return self._create_item_con_fecha(sin_fecha)
                except Exception:
                    pass
            return self._create_item_via_provider(sin_fecha)

        result = self._provider._normalize_issue(body)
        parent = payload.get("dest_parent_gitlab_iid")
        if parent:
            self._provider._link_parent(
                str(body.get("iid") or body.get("id") or ""), parent
            )
        return result

    def post_comment(self, item_iid: str, body: str, created_at: Optional[str] = None) -> dict:
        """Con `created_at` hace el POST directo para backdatear la nota.

        `GitLabTrackerProvider.post_comment` no expone ese campo, y la API v4 sí
        lo acepta en `POST /projects/:id/issues/:iid/notes` — "requires
        administrator or project/group owner rights", que el token cumple. Sin
        `created_at` se delega al provider, camino sin cambios.
        """
        if not created_at:
            return self._provider.post_comment(item_iid, body)

        proj_path = self._provider._client._project_path()
        try:
            resultado, _ = self._provider._client._request(
                "POST",
                f"/projects/{proj_path}/issues/{item_iid}/notes",
                json_body={"body": body, "created_at": created_at},
            )
            return resultado if isinstance(resultado, dict) else {}
        except Exception as exc:
            self._logger.warning(
                "post_comment: GitLab rechazó created_at=%r en el issue %s (%s). "
                "Se reintenta SIN backdating: la fecha real ya está en el cuerpo "
                "de la nota.",
                created_at, item_iid, exc,
            )
            return self._provider.post_comment(item_iid, body)

    def upload_attachment(self, file_path: str, filename: str) -> dict:
        return self._provider.upload_attachment(file_path, filename)

    def link_attachment(self, item_iid: str, attachment_meta: dict) -> dict:
        """Enlaza el adjunto en la descripción, dejando el MARKER al lado.

        `GitLabTrackerProvider.link_attachment` (`gitlab_provider.py:369`)
        concatena solo el markdown, sin ninguna huella de qué adjunto de
        origen es. Sin marker no hay forma de saber, en una corrida futura,
        si este adjunto ya se migró: la única defensa contra el duplicado
        pasaba a ser el nombre de archivo. Se inyecta el marker en el propio
        markdown (el caller lo pasa dentro de `attachment_meta["marker"]`,
        sin cambiar la firma que comparten las 3 implementaciones)."""
        marker = (attachment_meta or {}).get("marker") or ""
        if not marker:
            return self._provider.link_attachment(item_iid, attachment_meta)

        meta = dict(attachment_meta)
        markdown = meta.get("markdown") or meta.get("url") or ""
        meta["markdown"] = f"{markdown}\n{marker}" if markdown else marker
        return self._provider.link_attachment(item_iid, meta)

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

    def apply_item_state(
        self, item_iid: str, desired_state: str, updated_at: Optional[str] = None
    ) -> dict:
        """`PUT /projects/:id/issues/:iid` con `state_event` (+ `updated_at`).

        Deliberadamente NO reusa `GitLabTrackerProvider.update_item_state`
        (`gitlab_provider.py:243-294`) aunque ese método ya sepa emitir
        `state_event`: además de cerrar, **reescribe los labels del issue** con
        el state map interno de Stacky (`:275-282` filtra los `stacky::*` y
        agrega `mapping["label"]`). Aplicado a una issue migrada, eso
        contaminaría el esquema `status::`/`category::`/`priority::` de la
        migración y borraría trazabilidad. Además su `logical_state` es el
        vocabulario de Stacky (`functional`/`accepted`/`rejected`/
        `in_progress`), no `opened`/`closed`.

        Se replica el patrón de acceso al cliente HTTP interno que ya usa
        `create_issue_link` (mismo módulo), que a su vez replica
        `gitlab_provider._link_parent:122-126`.

        El cuerpo lleva ÚNICAMENTE `state_event`: cualquier campo extra en un
        `PUT` de GitLab lo sobrescribe, así que mandar `labels` o `description`
        acá sería una vía silenciosa de pisar datos ya migrados.
        """
        normalized = (desired_state or "").strip().lower()
        if normalized == "closed":
            state_event = "close"
        elif normalized == "opened":
            state_event = "reopen"
        else:
            raise ValueError(
                f"apply_item_state: desired_state={desired_state!r} inválido; "
                "se esperaba 'opened' o 'closed'."
            )

        cuerpo: dict = {"state_event": state_event}
        if updated_at:
            # `updated_at` SÍ lo acepta el PUT ("requires administrator or
            # project owner rights"). Va en el MISMO PUT que el cierre y por eso
            # esta pasada tiene que ser la ÚLTIMA escritura del pipeline:
            # cualquier nota o adjunto posterior volvería a poner `updated_at` en
            # `now()` y perderíamos la fidelidad recién ganada.
            cuerpo["updated_at"] = updated_at

        proj_path = self._provider._client._project_path()
        try:
            body, _ = self._provider._client._request(
                "PUT",
                f"/projects/{proj_path}/issues/{item_iid}",
                json_body=cuerpo,
            )
        except Exception:
            if not updated_at:
                raise
            # El cierre importa más que la fidelidad de `updated_at`: si la
            # instancia rechaza el backdating, se reintenta con el PUT mínimo.
            self._logger.warning(
                "apply_item_state: GitLab rechazó updated_at=%r en el issue %s. "
                "Se reintenta con el PUT mínimo (solo state_event).",
                updated_at, item_iid,
            )
            body, _ = self._provider._client._request(
                "PUT",
                f"/projects/{proj_path}/issues/{item_iid}",
                json_body={"state_event": state_event},
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

    def attachment_exists(self, item_iid: str, marker: str, filename: str = "") -> bool:
        """Idempotencia de adjuntos: ¿ya está este adjunto en la descripción?

        `link_attachment` escribe el adjunto EN LA DESCRIPCIÓN del issue, no
        como comentario, así que `comment_exists` no lo ve. Sin este chequeo,
        una segunda corrida vuelve a subir el binario y CONCATENA otra vez el
        markdown a la descripción (`gitlab_provider.py:379` hace
        `description + markdown`), duplicando el adjunto en silencio.

        Dos criterios, en orden:
          1. El `marker` (`<!-- stacky-migrated:mantis-file:P:I:F -->`), que es
             el identificador exacto y estable del adjunto de origen.
          2. Fallback por nombre de archivo dentro de un link `/uploads/`:
             los adjuntos migrados ANTES de que se empezara a escribir el
             marker no lo tienen, y sin este fallback se duplicarían.
        """
        proj_path = self._provider._client._project_path()
        try:
            current, _ = self._provider._client._request(
                "GET", f"/projects/{proj_path}/issues/{item_iid}"
            )
            description = (current or {}).get("description") or ""
        except Exception:
            # Ante la duda NO se declara "ya existe": devolver True acá
            # saltearía un adjunto que sí falta. Se devuelve False y el
            # chequeo real queda en el marker de la próxima corrida.
            return False

        if marker and marker in description:
            return True
        if filename:
            import re as _re

            for match in _re.finditer(r"\((/uploads/[^)]+)\)", description):
                if match.group(1).rstrip("/").endswith("/" + filename):
                    return True
        return False

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
        #  `{iid: "opened"|"closed"}` de los cambios de estado simulados, para
        #  que `fetch_open_items` los refleje (ver `apply_item_state`).
        self._simulated_states: dict[str, str] = {}
        #  `{titulo: id_ficticio}` de los milestones simulados.
        self._simulated_milestones: "dict[str, int]" = {}
        self._logger = logging.getLogger(_LOGGER_NAME)

    def _next_fake_id(self) -> str:
        self._counter += 1
        return f"dryrun-{self._counter}"

    def create_item(self, payload: dict) -> dict:
        fake_iid = self._next_fake_id()
        self._logger.info("[SIMULACRO] habría creado issue %s (title=%r)", fake_iid, payload.get("title"))
        self.simulated_ops.append({"op": "create_item", "payload": payload, "iid": fake_iid})
        return {"iid": fake_iid}

    def post_comment(self, item_iid: str, body: str, created_at: Optional[str] = None) -> dict:
        fake_id = self._next_fake_id()
        self._logger.info(
            "[SIMULACRO] habría comentado en issue %s%s",
            item_iid,
            f" con created_at={created_at}" if created_at else " (sin backdating)",
        )
        self.simulated_ops.append({
            "op": "post_comment", "item_iid": item_iid, "body": body,
            "created_at": created_at, "id": fake_id,
        })
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

    def ensure_milestone(self, title: str) -> Optional[int]:
        limpio = (title or "").strip()
        if not limpio:
            return None
        if limpio not in self._simulated_milestones:
            self._simulated_milestones[limpio] = 9000 + len(self._simulated_milestones)
            self._logger.info("[SIMULACRO] habria creado el milestone %r", limpio)
            self.simulated_ops.append({"op": "ensure_milestone", "title": limpio})
        return self._simulated_milestones[limpio]

    def apply_item_state(
        self, item_iid: str, desired_state: str, updated_at: Optional[str] = None
    ) -> dict:
        normalized = (desired_state or "").strip().lower()
        if normalized not in ("opened", "closed"):
            # Mismo contrato que la implementación real: un estado inválido
            # falla IGUAL en simulacro, para que el dry-run no dé por bueno
            # algo que la corrida real rechazaría.
            raise ValueError(
                f"apply_item_state: desired_state={desired_state!r} inválido; "
                "se esperaba 'opened' o 'closed'."
            )
        self._logger.info(
            "[SIMULACRO] habría puesto el issue %s en estado %s%s",
            item_iid, normalized,
            f" con updated_at={updated_at}" if updated_at else "",
        )
        self.simulated_ops.append({
            "op": "apply_item_state", "item_iid": str(item_iid),
            "state": normalized, "updated_at": updated_at,
        })
        # Se recuerda el estado simulado para que `fetch_open_items` lo refleje:
        # así una segunda pasada de estados en el mismo dry-run ve el cambio y
        # no vuelve a "aplicarlo" (ejercita la idempotencia sin tocar GitLab).
        self._simulated_states[str(item_iid)] = normalized
        return {"iid": str(item_iid), "state": normalized}

    def fetch_states(self) -> list[str]:
        return []

    def fetch_open_items(self) -> list[dict]:
        # Coherencia consigo mismo (decisión documentada, a criterio de
        # este batch): en vez de devolver `[]` fijo, refleja los
        # `create_item` ya simulados como "items" con `iid`+`description` —
        # así `hydrate_map_from_destination_mg` (F5) puede ejercitarse en
        # un dry-run end-to-end sin tocar GitLab real ni requerir un
        # segundo fake distinto solo para probar la rehidratación.
        #
        # `state` se incluye porque `migrator_mg_states.fetch_destination_states`
        # lo necesita. Default `"opened"`: un issue recién creado por la API de
        # GitLab nace abierto, así que ése es el estado fiel del simulacro.
        # LIMITACIÓN DECLARADA: el simulacro solo conoce los issues que ÉL
        # simuló crear — no ve las issues que ya existen en GitLab. Por eso
        # `execute --dry-run` no puede anticipar qué cerraría de una migración
        # previa; para eso hay que leer el destino real.
        return [
            {
                "iid": op["iid"],
                "description": (op.get("payload") or {}).get("description", ""),
                "state": self._simulated_states.get(str(op["iid"]), "opened"),
            }
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
