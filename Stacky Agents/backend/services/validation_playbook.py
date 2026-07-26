"""Plan 209 — Guía "Cómo validar esto (como usuario del sistema RS)".

Objeto canónico `ValidationPlaybook` con dos productores:
  - **A** (F1): el agente escribe la sección en su HTML (instrucción de prompt).
  - **B** (F3): relleno determinista por retrieval local (TF-IDF, sin LLM extra)
    cuando A faltó o quedó pobre.

Regla innegociable: **ningún paso sin fuente citada**. Sin evidencia se degrada
honestamente con `DEGRADED_MESSAGE`; nunca se inventa.

El mecanismo está acotado a agentes **user-facing** (`USER_FACING_AGENT_TYPES`):
el entregable de devops / `__critic__` / incident / pr_review / documenter /
evolution_mutator no es una feature de UI/negocio de RS que un novato pueda
validar, así que una guía ahí sería ruido y tokens desperdiciados.
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("stacky_agents.validation_playbook")


# ── Constantes compartidas por todas las fases ───────────────────────────────

SECTION_TITLE = "Cómo validar esto (como usuario del sistema RS)"

DEGRADED_MESSAGE = (
    "Estos pasos no pudieron verificarse contra la documentación del producto. "
    "Confirmá con un referente de RS antes de usarlos."
)

SECTION_MARKER = 'data-stacky="validation-playbook"'
MARKER_COMMENT = "<!-- stacky:validation-playbook v1 -->"

VALID_STATUSES = frozenset({"agent_provided", "enriched", "degraded", "disabled"})

# Allowlist de tipos de agente cuya salida es un cambio de producto RS validable
# por un usuario novato. Mismo patrón que el gate `agent_type != "incident"` de
# incident_autopublish. Los tipos verificados en agents/*.py que quedan FUERA por
# diseño: devops, __critic__, debug, pr_review, Documentador, evolution_mutator,
# incident, custom.
USER_FACING_AGENT_TYPES: frozenset[str] = frozenset(
    {"functional", "developer", "incident_dev", "qa", "technical", "business"}
)


def is_user_facing(agent_type: Optional[str]) -> bool:
    """Único punto de decisión de scope, compartido por A (F1) y B (F3)."""
    return bool(agent_type) and agent_type in USER_FACING_AGENT_TYPES


def flag_enabled() -> bool:
    """Lee la INSTANCIA `config.config` (no el módulo: el módulo devuelve el
    default y mataría el branch OFF). Fallback a env para deploys viejos."""
    try:
        from config import config as _cfg

        value = getattr(_cfg, "STACKY_VALIDATION_PLAYBOOK_ENABLED", None)
        if value is not None:
            return bool(value)
    except Exception:  # noqa: BLE001
        logger.debug("flag_enabled: no se pudo leer config.config", exc_info=True)
    return os.getenv("STACKY_VALIDATION_PLAYBOOK_ENABLED", "true").strip().lower() in (
        "1", "true", "yes", "on",
    )


# ── F1 (enfoque A) — instrucción que viaja en el system prompt ───────────────

VALIDATION_PLAYBOOK_INSTRUCTION = f"""## {SECTION_TITLE}

Al final de tu entregable agregá SIEMPRE una sección con este título exacto:
"{SECTION_TITLE}".

Contenido: pasos concretos de la interfaz/negocio del PRODUCTO RS del cliente
(pantallas, menús, campos, batch, consultas) que un usuario NOVATO puede seguir
para comprobar por sí mismo que este desarrollo funciona, SIN preguntarle a un
experto. Ejemplos del tipo de paso: "cómo entrar al detalle del cliente", "cómo
asignar una obligación y verla en la pantalla de inicio".

Reglas OBLIGATORIAS:
1. Cada paso DEBE apoyarse en la documentación que recibiste (bloque func-docs,
   descripción del épica, catálogo de procesos del cliente). Citá la fuente entre
   corchetes al final del paso, por ejemplo [func-docs: Alta de cliente].
2. Si NO tenés base documental para un paso, NO lo inventes. En su lugar escribí
   textualmente: "{DEGRADED_MESSAGE}"
3. Si tu entregable NO cambia nada visible para un usuario en la UI del producto
   RS (ej. refactor interno, cambio de batch sin efecto de pantalla), decilo así:
   "Este cambio no tiene validación visible en la UI de RS" y, si aplica, indicá
   la verificación técnica pertinente.
4. Envolvé la sección en este HTML para que el sistema la reconozca:
   <section {SECTION_MARKER} data-confidence="0.0-1.0">
     <h2>{SECTION_TITLE}</h2>
     <ol>
       <li data-source="func-docs:alta-cliente">Paso... <em>Resultado esperado:</em> ... [func-docs: Alta de cliente]</li>
     </ol>
     <p data-sources>Fuentes: ...</p>
   </section>
   Poné data-confidence según cuán sólida sea tu base documental (1.0 = docs
   explícitas; 0.4 o menos = dudoso, y en ese caso usá el texto de degradación).
5. NUNCA toques Azure DevOps por esto: es sólo texto en tu entregable."""


def validation_prompt_block(agent_type: Optional[str]) -> str:
    """Instrucción A si corresponde; `""` si la flag está OFF o el agente no es
    de producto (evita quemar input tokens en los agentes no user-facing)."""
    if not flag_enabled() or not is_user_facing(agent_type):
        return ""
    return VALIDATION_PLAYBOOK_INSTRUCTION


# ── Objeto canónico ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ValidationStep:
    n: int
    action: str
    expected_result: str
    source: str  # referencia citada, p.ej. "func-docs:alta-cliente" o "catalog:IncHost"

    def to_dict(self) -> dict:
        return {
            "n": int(self.n),
            "action": self.action,
            "expected_result": self.expected_result,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ValidationStep":
        d = d if isinstance(d, dict) else {}
        try:
            n = int(d.get("n") or 0)
        except (TypeError, ValueError):
            n = 0
        return cls(
            n=n,
            action=str(d.get("action") or ""),
            expected_result=str(d.get("expected_result") or ""),
            source=str(d.get("source") or ""),
        )


@dataclass(frozen=True)
class ValidationPlaybook:
    status: str  # "agent_provided" | "enriched" | "degraded" | "disabled"
    steps: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    confidence: float = 0.0
    degraded_reason: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status not in VALID_STATUSES:
            raise ValueError(
                f"status inválido: {self.status!r}. Aceptados: {sorted(VALID_STATUSES)}"
            )

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
            "sources": list(self.sources),
            "confidence": float(self.confidence),
            "degraded_reason": self.degraded_reason,
        }

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "ValidationPlaybook":
        """Defensivo: un dict inválido/ausente da un playbook `disabled`, nunca lanza."""
        if not isinstance(d, dict):
            return cls(status="disabled", steps=[], sources=[], confidence=0.0,
                       degraded_reason=None)
        status = d.get("status")
        if status not in VALID_STATUSES:
            status = "disabled"
        try:
            confidence = float(d.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        raw_steps = d.get("steps")
        steps = [ValidationStep.from_dict(s) for s in raw_steps] if isinstance(raw_steps, list) else []
        raw_sources = d.get("sources")
        sources = [str(s) for s in raw_sources] if isinstance(raw_sources, list) else []
        return cls(
            status=status,
            steps=steps,
            sources=sources,
            confidence=max(0.0, min(1.0, confidence)),
            degraded_reason=d.get("degraded_reason"),
        )


# ── F5 — sentinel anti-alucinación (PURO; usado también por assess_grounding) ─


def assert_no_invented_steps(pb: ValidationPlaybook) -> list:
    """Devuelve la lista de violaciones ("step N sin source"). Vacía = OK.

    NO lanza: `assess_grounding` la usa como filtro.
    """
    out: list = []
    try:
        for step in getattr(pb, "steps", None) or []:
            if not (getattr(step, "source", "") or "").strip():
                out.append(f"step {getattr(step, 'n', '?')} sin source")
    except Exception:  # noqa: BLE001
        logger.debug("assert_no_invented_steps falló (no crítico)", exc_info=True)
    return out


# ── Helpers de normalización de texto (comparación tolerante a acentos) ──────


def _fold(text: str) -> str:
    """minúsculas, sin acentos, espacios colapsados. Para comparar el mensaje de
    degradación aunque el modelo se coma las tildes."""
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(text))
    sin_acentos = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin_acentos).strip().lower()


_DEGRADED_FOLDED = _fold(DEGRADED_MESSAGE)


# ── F2 — gate determinista: detect + assess_grounding (advisory) ─────────────

_SECTION_RE = re.compile(
    r"<section[^>]*data-stacky\s*=\s*[\"']validation-playbook[\"'][^>]*>(.*?)</section>",
    re.IGNORECASE | re.DOTALL,
)
_CONFIDENCE_RE = re.compile(r"data-confidence\s*=\s*[\"']([^\"']*)[\"']", re.IGNORECASE)
_LI_RE = re.compile(r"<li([^>]*)>(.*?)</li>", re.IGNORECASE | re.DOTALL)
_DATA_SOURCE_RE = re.compile(r"data-source\s*=\s*[\"']([^\"']*)[\"']", re.IGNORECASE)
_SOURCES_P_RE = re.compile(r"<p[^>]*data-sources[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_EXPECTED_RE = re.compile(r"resultado\s+esperado\s*:?", re.IGNORECASE)


def _strip_tags(fragment: str) -> str:
    import html as _html

    text = _TAG_RE.sub(" ", fragment or "")
    return re.sub(r"\s+", " ", _html.unescape(text)).strip()


def _split_expected(text: str) -> tuple:
    """Parte "acción ... Resultado esperado: ..." en (acción, resultado)."""
    m = _EXPECTED_RE.search(text or "")
    if not m:
        return (text or "").strip(), ""
    return text[: m.start()].strip().rstrip(".").strip(), text[m.end():].strip()


def _parse_confidence(section_html: str) -> float:
    m = _CONFIDENCE_RE.search(section_html or "")
    if not m:
        return 0.5
    try:
        return max(0.0, min(1.0, float(m.group(1).strip())))
    except (TypeError, ValueError):
        return 0.5


def detect(html: Optional[str]) -> Optional[ValidationPlaybook]:
    """Parsea la sección del HTML del agente (enfoque A). Nunca lanza.

    Devuelve `None` si la sección no está (señal de que A no produjo nada ⇒ B).
    """
    try:
        if not html or SECTION_MARKER.split("=")[0] not in html or "validation-playbook" not in html:
            return None
        m = _SECTION_RE.search(html)
        # Tolerante: si el <section> está mal cerrado pero el marcador está, se
        # parsea el HTML entero antes que perder el trabajo del agente.
        body = m.group(1) if m else html
        head = html[: m.start(1)] if m else html

        if _DEGRADED_FOLDED and _DEGRADED_FOLDED in _fold(body):
            return ValidationPlaybook(status="degraded", steps=[], sources=[],
                                      confidence=0.0, degraded_reason="agent_declared")

        confidence = _parse_confidence(head)
        steps: list = []
        for idx, (attrs, inner) in enumerate(_LI_RE.findall(body), start=1):
            src_m = _DATA_SOURCE_RE.search(attrs or "")
            action, expected = _split_expected(_strip_tags(inner))
            steps.append(
                ValidationStep(
                    n=idx,
                    action=action,
                    expected_result=expected,
                    source=(src_m.group(1).strip() if src_m else ""),
                )
            )

        sources: list = []
        sm = _SOURCES_P_RE.search(body)
        if sm:
            raw = _strip_tags(sm.group(1))
            raw = re.sub(r"^\s*fuentes\s*:?\s*", "", raw, flags=re.IGNORECASE)
            sources = [p.strip() for p in re.split(r"[,;]", raw) if p.strip()]

        return ValidationPlaybook(status="agent_provided", steps=steps, sources=sources,
                                  confidence=confidence, degraded_reason=None)
    except Exception:  # noqa: BLE001
        logger.debug("detect falló (no crítico)", exc_info=True)
        return None


def _unknown_processes(text: Optional[str], process_catalog: Optional[list]) -> list:
    """Wrapper del detector de procesos fuera del catálogo.

    Import LAZY de `api.tickets` (6600+ líneas, blueprint): un import top-level
    acoplaría service→api y cargaría todo el módulo en cada composición de prompt
    y en el arranque. Si el import falla, se omiten solo estos warnings.
    """
    if not text or not process_catalog:
        return []
    try:
        from api.tickets import catalog_unknown_processes  # noqa: PLC0415

        return catalog_unknown_processes(text, process_catalog) or []
    except Exception:  # noqa: BLE001
        logger.debug("catalog_unknown_processes no disponible (no crítico)", exc_info=True)
        return []


def assess_grounding(
    pb: ValidationPlaybook,
    process_catalog: Optional[list],
    *,
    source_text: Optional[str] = None,
) -> tuple:
    """Evalúa el grounding del playbook y devuelve `(playbook, warnings)`.

    - Elimina los pasos sin `source` (advirtiendo por cada uno). Si no queda
      ninguno ⇒ `degraded`.
    - Con catálogo: un paso que cita un proceso ausente NO se publica como
      grounded. Sin catálogo, no opina (degradación honesta).
    - Nunca lanza, nunca bloquea.
    """
    warnings: list = []
    try:
        original = list(getattr(pb, "steps", None) or [])
        kept: list = []
        for step in original:
            if (step.source or "").strip():
                kept.append(step)
            else:
                warnings.append(
                    f"validation_playbook.ungrounded_step: paso {step.n} sin fuente"
                )

        if process_catalog:
            global_unknown = _unknown_processes(source_text, process_catalog)
            if global_unknown:
                warnings.append(
                    f"validation_playbook.process_not_in_catalog: {global_unknown}"
                )
            survivors: list = []
            for step in kept:
                unknown = _unknown_processes(f"{step.action} {step.expected_result}", process_catalog)
                if unknown:
                    if not global_unknown:
                        warnings.append(
                            f"validation_playbook.process_not_in_catalog: {unknown}"
                        )
                    continue
                survivors.append(step)
            kept = survivors

        if original and not kept:
            return (
                ValidationPlaybook(status="degraded", steps=[], sources=list(pb.sources),
                                   confidence=0.0, degraded_reason="ungrounded_steps"),
                warnings,
            )
        renumbered = [
            ValidationStep(n=i, action=s.action, expected_result=s.expected_result, source=s.source)
            for i, s in enumerate(kept, start=1)
        ]
        return (
            ValidationPlaybook(status=pb.status, steps=renumbered, sources=list(pb.sources),
                               confidence=pb.confidence, degraded_reason=pb.degraded_reason),
            warnings,
        )
    except Exception:  # noqa: BLE001
        logger.debug("assess_grounding falló (no crítico)", exc_info=True)
        return pb, warnings


# ── F3 (enfoque B) — relleno determinista por retrieval local ────────────────

_SNIPPET_MAX = 220


def _snippet(text: str) -> str:
    clean = re.sub(r"\s+", " ", (text or "")).strip()
    return clean if len(clean) <= _SNIPPET_MAX else clean[: _SNIPPET_MAX - 1].rstrip() + "…"


def build_from_grounding(
    *,
    ticket_title: str,
    ticket_text: str,
    project_name: Optional[str],
    process_catalog: Optional[list],
) -> ValidationPlaybook:
    """Construye el playbook desde el grounding LOCAL (TF-IDF, sin red, sin LLM).

    Regla dura: cada paso nace de un fragmento recuperado y cita su fuente. Sin
    fragmentos ⇒ `degraded` con `no_grounding`. B NUNCA inventa pasos.
    """
    hits: list = []

    # Retrieval 1 — documentación funcional del cliente (DocConsultor vivo).
    try:
        if project_name:
            from services import docs_rag  # noqa: PLC0415

            for h in docs_rag.search(project_name, f"cómo validar {ticket_title}", top_k=5) or []:
                ref = (getattr(h, "section_heading", "") or getattr(h, "file_path", "") or "doc").strip()
                hits.append((f"func-docs:{ref}", getattr(h, "chunk_text", "") or ""))
    except Exception:  # noqa: BLE001
        logger.debug("docs_rag.search no disponible (no crítico)", exc_info=True)

    # Retrieval 2 — catálogo de procesos del perfil del cliente.
    try:
        if process_catalog:
            from services import rag_retriever  # noqa: PLC0415

            chunks = rag_retriever.chunks_from_process_catalog(process_catalog)
            if chunks:
                # content_hash permite reusar el índice TF-IDF entre corridas en
                # vez de reconstruirlo en el hilo de completación cada vez.
                index = rag_retriever.build_index(
                    chunks, content_hash=f"{project_name}:{len(process_catalog)}"
                )
                query = f"{ticket_title} {ticket_text}".strip()
                for chunk, score in rag_retriever.retrieve(index, query, top_k=5) or []:
                    if score <= 0:
                        continue
                    name = (chunk.payload or {}).get("name") or chunk.id
                    hits.append((f"catalog:{name}", chunk.text))
    except Exception:  # noqa: BLE001
        logger.debug("rag_retriever no disponible (no crítico)", exc_info=True)

    if not hits:
        return ValidationPlaybook(status="degraded", steps=[], sources=[], confidence=0.0,
                                  degraded_reason="no_grounding")

    steps: list = []
    sources: list = []
    for i, (ref, text) in enumerate(hits, start=1):
        if ref not in sources:
            sources.append(ref)
        steps.append(
            ValidationStep(
                n=i,
                action=f"Verificá en el producto lo que describe esta fuente: «{_snippet(text)}»",
                expected_result=(
                    "El comportamiento del sistema coincide con lo documentado en la fuente citada."
                ),
                source=ref,
            )
        )

    pb = ValidationPlaybook(
        status="enriched",
        steps=steps,
        sources=sources,
        # Heurística acotada y declarada como tal: más fuentes ⇒ más confianza.
        confidence=min(1.0, 0.3 + 0.1 * len(sources)),
        degraded_reason=None,
    )
    # Filtro de seguridad: si algo quedó sin fuente, se elimina (no debería pasar).
    pb, _warnings = assess_grounding(pb, None)
    return pb


def render_playbook_html(pb: ValidationPlaybook) -> str:
    """Serializa el objeto canónico al HTML de la sección.

    Alcance real: **no** es el renderer de la UI (F4 renderiza JSX desde el objeto,
    sin `dangerouslySetInnerHTML`). Sirve como oráculo de tests y como generador
    del camino ADO futuro. El invariante es "un solo objeto canónico → vistas
    equivalentes".
    """
    import html as _html

    def esc(value) -> str:
        return _html.escape(str(value or ""), quote=True)

    head = (
        f"{MARKER_COMMENT}\n"
        f'<section {SECTION_MARKER} data-confidence="{float(pb.confidence):.2f}">\n'
        f"  <h2>{esc(SECTION_TITLE)}</h2>\n"
    )
    if pb.status == "degraded" or not pb.steps:
        return head + f'  <p class="stacky-degraded">{esc(DEGRADED_MESSAGE)}</p>\n</section>'

    filas = "\n".join(
        f'    <li data-source="{esc(s.source)}">{esc(s.action)} '
        f"<em>Resultado esperado:</em> {esc(s.expected_result)} [{esc(s.source)}]</li>"
        for s in pb.steps
    )
    fuentes = esc(", ".join(pb.sources)) if pb.sources else "—"
    return (
        head
        + "  <ol>\n"
        + filas
        + "\n  </ol>\n"
        + f"  <p data-sources>Fuentes: {fuentes}</p>\n</section>"
    )


def compute_and_attach(
    *,
    execution,
    agent_type: Optional[str],
    html: Optional[str],
    project_name: Optional[str],
    process_catalog: Optional[list],
) -> ValidationPlaybook:
    """Núcleo testeable: resuelve el playbook (A o B) y lo persiste en
    `execution.metadata_json`. Nunca lanza."""
    if not flag_enabled() or not is_user_facing(agent_type):
        return ValidationPlaybook(status="disabled", steps=[], sources=[], confidence=0.0,
                                  degraded_reason="not_applicable")
    try:
        pb = detect(html)
        if pb is None or not pb.steps:
            ticket = getattr(execution, "ticket", None)
            pb = build_from_grounding(
                ticket_title=str(getattr(ticket, "title", "") or ""),
                ticket_text=str(getattr(ticket, "description", "") or ""),
                project_name=project_name,
                process_catalog=process_catalog,
            )
        pb, warnings = assess_grounding(pb, process_catalog, source_text=html)

        for warning in warnings:
            logger.warning("%s", warning)

        # C3 — patrón EXACTO de _close_execution: metadata_json es una columna Text
        # (un str). Un item-assignment sobre él tira TypeError que el post-hook
        # advisory se traga en silencio ⇒ feature muerta sin señal.
        import json as _json

        meta: dict = {}
        raw = getattr(execution, "metadata_json", None)
        if raw:
            try:
                loaded = _json.loads(raw)
                meta = loaded if isinstance(loaded, dict) else {}
            except (ValueError, TypeError):
                meta = {}
        meta["validation_playbook"] = pb.to_dict()
        execution.metadata_json = _json.dumps(meta, ensure_ascii=False, default=str)
        return pb
    except Exception:  # noqa: BLE001
        logger.debug("compute_and_attach falló (no crítico)", exc_info=True)
        return ValidationPlaybook(status="degraded", steps=[], sources=[], confidence=0.0,
                                  degraded_reason="exception")


def validation_playbook_post_hook(
    *, ticket_id, execution_id, final_status, agent_type=None, error=None, **kwargs
) -> None:
    """Seam runtime-agnóstico: se registra en `ticket_status.on_execution_end`, por
    el que terminan los 3 runners y el output_watcher. Advisory: nunca bloquea."""
    # Gate ANTES de abrir sesión o leer disco: los agentes no-producto no pagan I/O.
    if not flag_enabled() or not is_user_facing(agent_type):
        return
    try:
        import db  # noqa: PLC0415  (el helper vive en db.py, NO en models.py)
        from models import AgentExecution  # noqa: PLC0415
        from services import agent_html_output  # noqa: PLC0415

        with db.session_scope() as session:
            execution = session.get(AgentExecution, execution_id) if execution_id else None
            if execution is None:
                return
            ticket = getattr(execution, "ticket", None)
            if ticket is None:
                return  # task borrada (trap conocida)
            ado_id = getattr(ticket, "ado_id", None)
            project = getattr(ticket, "stacky_project_name", None)

            html = None
            if ado_id:
                try:
                    hint = getattr(execution, "html_output_path", None)
                    html = agent_html_output.read_and_validate(ado_id, hint=hint).html
                except Exception:  # noqa: BLE001 — NOT_FOUND/EMPTY/... ⇒ decide B
                    html = None

            catalog: list = []
            try:
                from services.client_profile import load_client_profile  # noqa: PLC0415

                catalog = (load_client_profile(project) or {}).get("process_catalog") or []
            except Exception:  # noqa: BLE001
                catalog = []

            compute_and_attach(
                execution=execution,
                agent_type=agent_type,
                html=html,
                project_name=project,
                process_catalog=catalog,
            )
    except Exception:  # noqa: BLE001
        logger.debug("validation_playbook_post_hook falló (no crítico)", exc_info=True)


def register(register_post_hook) -> None:
    """Espeja incident_autopublish.register: register_post_hook == ticket_status.register_post_hook."""
    register_post_hook(validation_playbook_post_hook)
