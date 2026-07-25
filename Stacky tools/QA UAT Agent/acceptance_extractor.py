"""acceptance_extractor.py — Criterios de aceptacion testeables (Plan 240 F6).

100% DETERMINISTA (parseo estructural + heuristicas del dominio RS). Cero LLM =>
identico en los 3 runtimes.

(C15) PARSEO ESTRUCTURAL, no heuristico. Verificado el 2026-07-25 en los tickets 367,
366, 57 y 61: System.Description trae SIEMPRE una estructura canonica de headings
h1-h6 (SIN acentos) y los items son <li>. El campo
Microsoft.VSTS.Common.AcceptanceCriteria NO EXISTE en este proyecto (0 chars en los 4
tickets sondeados): los criterios viven dentro de System.Description bajo el heading
"CRITERIOS DE ACEPTACION".
"""
from __future__ import annotations

import html as _html
import re
from typing import Optional

_CANONICAL_SECTIONS = (
    "RESUMEN EJECUTIVO", "CONTEXTO DE NEGOCIO", "ANALISIS FUNCIONAL",
    "ANALISIS TECNICO", "PASOS DE REPRODUCCION", "CRITERIOS DE ACEPTACION",
    "ARCHIVOS Y MODULOS PROBABLES", "EPICA RELACIONADA", "PRIORIDAD Y ESTIMACION",
)

_SCREEN_RE = re.compile(r"\b(Frm[A-Za-z0-9]+)\.aspx\b")

# Sinonimos funcionales -> pantalla, verificados contra la app real.
_SCREEN_HINTS = {
    "busqueda de clientes": "FrmBusqueda.aspx",
    "detalle de cliente": "FrmDetalleClie.aspx",
    "agenda personal": "FrmAgenda.aspx",
    "agenda de grupo": "FrmAgendaEquipo.aspx",
    "agenda del equipo": "FrmAgendaEquipo.aspx",
    "reasignacion manual": "FrmAsignarLote.aspx",
    "asignar lote": "FrmAsignarLote.aspx",
    "agenda judicial": "FrmAgendaJudicial.aspx",
    "busqueda judicial": "FrmBusquedaJudicial.aspx",
    "administrador": "FrmAdministrador.aspx",
    # Sinonimos funcionales adicionales verificados contra los tickets reales
    # (RF-001/RF-003/EP-01/EP-08 hablan del "Filtro de Agenda", no de la pantalla).
    "filtro de agenda": "FrmAgenda.aspx",
    "resumen de agenda": "FrmAgenda.aspx",
    "agenda web": "FrmAgenda.aspx",
    "busqueda avanzada": "FrmAgenda.aspx",
    "grilla de agenda": "FrmAgenda.aspx",
    "ficha del cliente": "FrmDetalleClie.aspx",
    "detalle del cliente": "FrmDetalleClie.aspx",
    "gestiones": "FrmDetalleClie.aspx",
    "telefonos": "FrmDetalleClie.aspx",
    "contactos": "FrmDetalleClie.aspx",
}

# Tipos de criterio reconocidos, en orden de precedencia.
_KIND_PATTERNS: tuple[tuple[str, str], ...] = (
    ("maxlength", r"maxlength|longitud\s+m[aá]xima|se\s+trunca|truncamiento|admite\s+hasta\s+\d+\s+caracteres|\d+\s+caracteres"),
    ("no_error", r"error\s+ajax|input\s+string\s+was\s+not|excepci[oó]n|sin\s+error(es)?\b"),
    ("absence", r"duplicad[ao]|repetid[ao]|no\s+debe\s+aparecer|no\s+se\s+muestra|sin\s+regresi[oó]n"),
    ("ordering", r"orden(ad[ao]|amiento)?\b|ordenar\s+por|de\s+mayor\s+a\s+menor|por\s+fecha\s+de"),
    ("catalog", r"cat[aá]logo|lista\s+desplegable|combo\b|debe\s+incluir|incluye\s+las\s+opciones"),
    ("color", r"\bcolor\b|\brojo\b|\bverde\b|\bchip\b|sem[aá]foro"),
    ("presence", r"debe\s+mostrar|debe\s+aparecer|se\s+visualiza|muestra\b|ausente|falta\b|no\s+existe"),
    ("value", r"debe\s+ser\b|igual\s+a\b|debe\s+indicar|calcula|persiste|retorna\b"),
)

_CA_ID_RE = re.compile(r"^\s*(CA[-_ ]?\d{1,3}|AC[-_ ]?\d{1,3}|P\d{2,3})\s*[:.\)-]\s*", re.I)
_EXPECTED_NUM_RE = re.compile(r"(?:hasta|de|=|:)\s*(\d{1,4})\s*(?:caracteres|chars)?", re.I)
_QUOTED_RE = re.compile(r"[\"“”']([^\"“”']{2,60})[\"“”']")


def _clean_text(raw: str) -> str:
    """Quita tags, resuelve entidades HTML y colapsa espacios."""
    if not raw:
        return ""
    txt = re.sub(r"<br\s*/?>", " ", raw, flags=re.I)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = _html.unescape(txt)
    txt = txt.replace("\xa0", " ")
    return re.sub(r"\s+", " ", txt).strip()


def split_sections(html_desc: str) -> dict:
    """Parte el HTML por headings h1-h6 -> {HEADING_UPPER: html_del_bloque}.

    CASO BORDE PROBADO (ticket 367): la descripcion DUPLICA todo el bloque de
    headings; gana SIEMPRE la PRIMERA aparicion. El texto anterior al primer heading
    es preambulo espurio y se DESCARTA. NUNCA lanza.
    """
    if not html_desc:
        return {}
    try:
        parts = re.split(r"<h[1-6][^>]*>(.*?)</h[1-6]>", html_desc, flags=re.I | re.S)
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, str] = {}
    i = 1
    while i < len(parts) - 1:
        head = _clean_text(parts[i]).upper()
        body = parts[i + 1]
        if head and head not in out:      # primera aparicion gana
            out[head] = body
        i += 2
    return out


def _li_items(block_html: Optional[str]) -> list[str]:
    """Extrae y limpia los <li> de un bloque; si no hay, parte el texto plano."""
    if not block_html:
        return []
    lis = re.findall(r"<li[^>]*>(.*?)</li>", block_html, flags=re.I | re.S)
    items = [_clean_text(li) for li in lis]
    items = [x for x in items if x]
    if items:
        return items
    flat = _clean_text(block_html)
    parts = [p.strip() for p in re.split(r"(?<=[.;])\s+", flat)]
    return [p for p in parts if len(p.split()) >= 4]


def _kind_of(text: str) -> str:
    low = text.lower()
    for kind, pat in _KIND_PATTERNS:
        if re.search(pat, low, re.I):
            return kind
    # Un criterio explicito del ticket JAMAS se descarta (descartarlo inflaria el
    # falso PASS que este plan viene a matar).
    return "assertion"


def _screen_of(text: str, title: str) -> Optional[str]:
    m = _SCREEN_RE.search(text)
    if m:
        return m.group(0)
    m = _SCREEN_RE.search(title or "")
    if m:
        return m.group(0)
    low = f"{text} {title}".lower()
    for syn, screen in _SCREEN_HINTS.items():
        if syn in low:
            return screen
    return None


def _expected_of(text: str) -> Optional[str]:
    m = _EXPECTED_NUM_RE.search(text)
    if m:
        return m.group(1)
    m = re.search(r"maxlength\s*=\s*(\d+)", text, re.I)
    if m:
        return m.group(1)
    return None


def _tokens_of(text: str) -> list[str]:
    return [t.strip() for t in _QUOTED_RE.findall(text) if t.strip()][:8]


def extract_acceptance(work_item: dict) -> dict:
    """Extrae criterios testeables de un work item. NUNCA lanza."""
    empty = {"ok": True, "criteria": [], "repro_steps": [], "screens": [],
             "confidence": "low", "sections_found": [], "notes": []}
    try:
        fields = (work_item or {}).get("fields") or {}
        title = str(fields.get("System.Title") or "")
        desc = str(fields.get("System.Description") or "")
        ac_field = str(fields.get("Microsoft.VSTS.Common.AcceptanceCriteria") or "")
        secs = split_sections(desc)
        sections_found = [s for s in _CANONICAL_SECTIONS if s in secs]
        notes: list[str] = []

        crit_block = secs.get("CRITERIOS DE ACEPTACION")
        raw_criteria = _li_items(crit_block)
        confidence = "low"
        if raw_criteria:
            confidence = "high"
        elif ac_field:
            raw_criteria = _li_items(ac_field)
            confidence = "high" if raw_criteria else "medium"

        if not raw_criteria:
            # Fallback heuristico: ANALISIS FUNCIONAL + titulo.
            notes.append("sin seccion CRITERIOS DE ACEPTACION: modo heuristico")
            fallback = _li_items(secs.get("ANALISIS FUNCIONAL")) or []
            if title:
                fallback = [title] + fallback
            raw_criteria = [t for t in fallback if len(t.split()) >= 3][:6]
            confidence = "medium" if secs else "low"

        criteria = []
        for idx, text in enumerate(raw_criteria, start=1):
            m = _CA_ID_RE.match(text)
            if m:
                cid = re.sub(r"[_ ]", "-", m.group(1).upper())
                body = text[m.end():].strip()
            else:
                cid = f"AC-{idx:02d}"
                body = text
            criteria.append({
                "id": cid,
                "text": body or text,
                "kind": _kind_of(body or text),
                "screen_hint": _screen_of(body or text, title),
                "tokens": _tokens_of(body or text),
                "expected": _expected_of(body or text),
            })

        repro_steps = _li_items(secs.get("PASOS DE REPRODUCCION"))

        screens: list[str] = []
        for src in [title] + [c["text"] for c in criteria] + repro_steps:
            for m in _SCREEN_RE.finditer(src or ""):
                if m.group(0) not in screens:
                    screens.append(m.group(0))
        for c in criteria:
            if c["screen_hint"] and c["screen_hint"] not in screens:
                screens.append(c["screen_hint"])

        return {"ok": True, "criteria": criteria, "repro_steps": repro_steps,
                "screens": screens, "confidence": confidence,
                "sections_found": sections_found, "notes": notes}
    except Exception as exc:  # noqa: BLE001
        out = dict(empty)
        out["notes"] = [f"extraction_failed: {type(exc).__name__}: {exc}"]
        return out


def build_plan_from_description(work_item: dict, primary_screen: Optional[str] = None) -> list:
    """Convierte los criterios en items de 'plan de pruebas' del reader existente.

    Shape espejo de uat_ticket_reader._extract_plan_pruebas: {id, descripcion,
    datos?, esperado?}. Reuso, no reescritura: el reader lo consume sin cambios.

    primary_screen: si se pasa, se EXCLUYEN los criterios de otras pantallas.
    Motivo (verificado en vivo, ticket 367 CA-02): el compilador fuerza la pantalla
    de scope a TODOS los escenarios, asi que un criterio de FrmBusquedaJudicial
    terminaba ejecutandose contra FrmBusqueda y fallando => FALSO NEGATIVO. Un
    criterio de otra pantalla es FUERA DE ALCANCE de este run, no un defecto.
    """
    acc = extract_acceptance(work_item)
    steps = acc.get("repro_steps") or []
    datos = " | ".join(steps[:3])[:400] if steps else None
    criteria = acc.get("criteria") or []
    if primary_screen:
        in_scope = [c for c in criteria
                    if not c.get("screen_hint") or c.get("screen_hint") == primary_screen]
        if in_scope:                      # nunca dejar el plan vacio por filtrar
            criteria = in_scope
    plan = []
    for i, c in enumerate(criteria, start=1):
        item = {"id": f"P{i:02d}", "descripcion": c["text"][:300]}
        # REGLA ANTI-FALSO-NEGATIVO: `esperado` se convierte aguas abajo en un oraculo
        # de TEXTO LITERAL sobre la pagina. Volcar la prosa del criterio ahi genera
        # basura verificable: el criterio "retorna el cliente esperado" produjo
        # expect(body).toContainText('Cliente esperado') y un FAIL falso (observado en
        # vivo, ticket 367 P03). Solo se emite `esperado` cuando hay un valor concreto
        # (numero citado o literal entrecomillado); si no, el criterio queda como
        # navegacion + llegada y el veredicto funcional lo marca not_verifiable.
        concrete = c.get("expected") or (c.get("tokens") or [None])[0]
        if concrete:
            item["esperado"] = str(concrete)[:120]
        else:
            item["verificable"] = False
        if datos:
            item["datos"] = datos
        if c.get("screen_hint"):
            item["pantalla"] = c["screen_hint"]
        if c.get("kind"):
            item["kind"] = c["kind"]
        if c.get("id"):
            item["criterio_id"] = c["id"]
        plan.append(item)
    return plan
