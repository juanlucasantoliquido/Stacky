"""Guarded Codex Browser QA UAT run specification builder."""
from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class BrowserRunInput:
    ticket_id: int
    ticket_ado_id: int | None
    ticket_title: str
    ticket_state: str | None
    ticket_url: str | None
    allowed_base_url: str
    context: dict[str, Any]
    operator_note: str | None = None
    max_scenarios: int = 16


def build_guarded_browser_spec(data: BrowserRunInput) -> dict[str, Any]:
    candidates = list(data.context.get("plan_candidates") or [])
    scenarios, used_sources = _extract_scenarios_from_candidates(
        candidates,
        max_scenarios=max(1, min(data.max_scenarios, 30)),
    )
    if not scenarios:
        scenarios = [_blocked_plan_review_scenario()]

    guardrails = _build_guardrails(data.allowed_base_url)
    spec: dict[str, Any] = {
        "schema_version": "stacky.qa_browser_run_spec.v1",
        "created_at": _utcnow(),
        "ticket": {
            "id": data.ticket_id,
            "ado_id": data.ticket_ado_id,
            "title": data.ticket_title,
            "state": data.ticket_state,
            "url": data.ticket_url,
        },
        "operator_note": data.operator_note,
        "plan_source": {
            "used_sources": used_sources,
            "candidate_count": len(candidates),
            "source_policy": "description_comments_attachments_then_local_executions",
        },
        "context_stats": data.context.get("stats") or {},
        "guardrails": guardrails,
        "scenarios": scenarios,
        "runner_contract": {
            "runtime": "codex_browser_visible",
            "api": {
                "spec": "/api/qa-browser/runs/{execution_id}/spec",
                "events": "/api/qa-browser/runs/{execution_id}/events",
                "evidence": "/api/qa-browser/runs/{execution_id}/evidence",
                "complete": "/api/qa-browser/runs/{execution_id}/complete",
            },
            "must_publish_ado_comment": True,
            "completion_payload": {
                "verdict": "PASS | FAIL | BLOCKED | MIXED",
                "summary": "texto corto",
                "scenarios": [
                    {
                        "scenario_id": "QA-UAT-001",
                        "verdict": "PASS | FAIL | BLOCKED",
                        "steps_executed": [],
                        "expected": "",
                        "actual": "",
                        "evidence": [],
                    }
                ],
            },
        },
    }
    spec["markdown"] = render_spec_markdown(spec)
    spec["codex_browser_prompt"] = build_codex_browser_prompt(spec)
    return spec


def render_spec_markdown(spec: dict[str, Any]) -> str:
    ticket = spec["ticket"]
    guardrails = spec["guardrails"]
    lines: list[str] = [
        "# QA UAT Codex Browser",
        "",
        f"Ticket: ADO-{ticket.get('ado_id') or ticket['id']} - {ticket['title']}",
        f"Estado: {ticket.get('state') or '-'}",
        f"Browser: `{guardrails['browser']}`",
        f"URL inicial: `{guardrails['start_url']}`",
        "",
        "## Guardrails",
        "",
        f"- Origen permitido: `{', '.join(guardrails['allowed_origins'])}`",
        "- Cada accion visible debe estar asociada a un `scenario_id` y `step_id`.",
        "- Si la pantalla no coincide con el plan, detener y marcar BLOCKED.",
        "- Si aparece login, permisos, modal inesperado o navegacion externa, detener.",
        "- No publicar en ADO desde el browser; Stacky publica al completar.",
        "",
        "## Escenarios",
        "",
    ]
    for scenario in spec["scenarios"]:
        lines.append(f"### {scenario['scenario_id']} - {scenario['title']}")
        lines.append(f"Fuente: {scenario['source']['title']}")
        if scenario.get("data_requirements"):
            lines.append(f"Datos: {scenario['data_requirements']}")
        lines.append("")
        for step in scenario["steps"]:
            lines.append(f"- `{step['step_id']}` {step['instruction']}")
        lines.append("")
        lines.append("Assertions:")
        for assertion in scenario["assertions"]:
            lines.append(f"- {assertion}")
        lines.append("")
    lines.extend(
        [
            "## Publicacion ADO",
            "",
            "Al cerrar el run, Stacky debe publicar SIEMPRE un comentario en ADO con",
            "pruebas realizadas, resultado por escenario y evidencia.",
        ]
    )
    return "\n".join(lines)


def build_codex_browser_prompt(spec: dict[str, Any]) -> str:
    ticket = spec["ticket"]
    execution_id = spec.get("execution_id") or "{execution_id}"
    api_base_url = str(spec.get("stacky_api_base_url") or "").rstrip("/")
    endpoint_prefix = api_base_url if api_base_url else ""
    spec_endpoint = f"{endpoint_prefix}/api/qa-browser/runs/{execution_id}/spec"
    events_endpoint = f"{endpoint_prefix}/api/qa-browser/runs/{execution_id}/events"
    evidence_endpoint = f"{endpoint_prefix}/api/qa-browser/runs/{execution_id}/evidence"
    complete_endpoint = f"{endpoint_prefix}/api/qa-browser/runs/{execution_id}/complete"
    return f"""Ejecuta el QA UAT visible con el navegador de Codex para ADO-{ticket.get('ado_id')}.

Contrato obligatorio:
- Usa el navegador visible de Codex.
- Si este runtime no expone navegador visible, usa automatizacion browser/Playwright local contra la URL inicial del spec.
- Lee y respeta el spec del run de Stacky.
- Ejecuta solo los escenarios y pasos listados.
- No inventes pruebas fuera del plan.
- No modifiques archivos del repo ni datos fuera de las acciones explicitamente pedidas por el plan.
- Registra eventos en Stacky despues de cada accion relevante.
- Captura evidencia suficiente por escenario.
- Al terminar, llama al endpoint de complete para que Stacky publique SIEMPRE el comentario en ADO.

Run Stacky: `{execution_id}`

Endpoints del run:
- GET `{spec_endpoint}`
- POST `{events_endpoint}`
- POST `{evidence_endpoint}`
- POST `{complete_endpoint}`

Formato minimo para empezar:
1. POST events con `type=browser.started`.
2. Navega a `spec.guardrails.start_url`.
3. Por cada paso ejecutado, POST events y evidencia.
4. POST complete con `verdict`, `summary` y resultados por escenario.

Spec embebido:

```json
{dumps_spec(spec)}
```
"""


def build_ado_comment_html(
    *,
    execution_id: int,
    spec: dict[str, Any],
    result: dict[str, Any],
    publish_error: str | None = None,
) -> str:
    ticket = spec["ticket"]
    verdict = str(result.get("verdict") or "BLOCKED").upper()
    summary = result.get("summary") or "Sin resumen informado por el runner."
    scenarios = result.get("scenarios") or []
    comment_hash = _hash_for_comment(spec, result)

    rows: list[str] = []
    for item in scenarios:
        sid = html.escape(str(item.get("scenario_id") or "-"))
        item_verdict = html.escape(str(item.get("verdict") or "BLOCKED"))
        expected = html.escape(str(item.get("expected") or ""))
        actual = html.escape(str(item.get("actual") or ""))
        evidence = item.get("evidence") or []
        evidence_html = "".join(
            f"<li>{html.escape(str(ev))}</li>" for ev in evidence[:20]
        ) or "<li>Sin evidencia declarada</li>"
        rows.append(
            "<tr>"
            f"<td><strong>{sid}</strong></td>"
            f"<td>{item_verdict}</td>"
            f"<td>{expected}</td>"
            f"<td>{actual}</td>"
            f"<td><ul>{evidence_html}</ul></td>"
            "</tr>"
        )

    if not rows:
        rows.append(
            "<tr><td colspan=\"5\">No se informaron escenarios ejecutados.</td></tr>"
        )

    publish_note = ""
    if publish_error:
        publish_note = (
            "<p><strong>Advertencia:</strong> hubo un error al publicar este comentario: "
            f"{html.escape(publish_error)}</p>"
        )

    used_sources = spec.get("plan_source", {}).get("used_sources") or []
    sources_html = "".join(
        f"<li>{html.escape(src.get('title') or src.get('source_id') or '-')}</li>"
        for src in used_sources
    ) or "<li>Sin fuente identificada</li>"

    return f"""
<!-- stacky-qa-browser-uat:run id="{execution_id}" hash="{comment_hash}" -->
<h2>QA UAT Codex Browser - ADO-{html.escape(str(ticket.get('ado_id') or ticket.get('id')))}</h2>
<p><strong>Veredicto global:</strong> {html.escape(verdict)}</p>
<p><strong>Resumen:</strong> {html.escape(str(summary))}</p>
<p><strong>Run Stacky:</strong> #{execution_id}</p>
<p><strong>Fecha:</strong> {html.escape(_utcnow())}</p>
{publish_note}
<h3>Fuentes usadas para armar el plan</h3>
<ul>{sources_html}</ul>
<h3>Resultados por escenario</h3>
<table>
  <thead>
    <tr>
      <th>Escenario</th>
      <th>Resultado</th>
      <th>Esperado</th>
      <th>Actual</th>
      <th>Evidencia</th>
    </tr>
  </thead>
  <tbody>
    {''.join(rows)}
  </tbody>
</table>
<p><em>Comentario publicado automaticamente por Stacky Agents al cerrar TEST QA UAT CODEX.</em></p>
""".strip()


def dumps_spec(spec: dict[str, Any]) -> str:
    safe = dict(spec)
    safe.pop("codex_browser_prompt", None)
    return json.dumps(safe, ensure_ascii=False, indent=2)


def _build_guardrails(allowed_base_url: str) -> dict[str, Any]:
    return {
        "mode": "guarded_visible_browser",
        "browser": "codex_browser",
        "allowed_origins": [_origin(allowed_base_url)],
        "start_url": allowed_base_url,
        "require_scenario_id_for_every_action": True,
        "require_step_id_for_every_action": True,
        "stop_on_unplanned_screen": True,
        "stop_on_unexpected_modal": True,
        "stop_on_auth_or_permission_prompt": True,
        "stop_on_external_navigation": True,
        "ado_comment_policy": "always_publish_on_complete",
        "forbidden_actions": [
            "publish_to_ado_from_browser",
            "change_ado_state",
            "delete_records",
            "bulk_update",
            "send_email",
            "payment_or_billing_action",
            "change_credentials",
            "execute_sql_or_seed_data",
            "upload_files",
            "download_sensitive_data",
        ],
        "evidence_required": [
            "screenshot_before_each_scenario",
            "screenshot_after_each_assertion",
            "visible_text_or_dom_snapshot_for_assertions",
            "final_verdict_per_scenario",
        ],
    }


def _extract_scenarios_from_candidates(
    candidates: list[dict[str, Any]],
    *,
    max_scenarios: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    scenarios: list[dict[str, Any]] = []
    used_sources: list[dict[str, Any]] = []
    seen: set[str] = set()

    for candidate in sorted(candidates, key=lambda c: c.get("confidence", 0), reverse=True):
        if len(scenarios) >= max_scenarios:
            break
        source = {
            "kind": candidate.get("kind"),
            "title": candidate.get("title"),
            "source_id": candidate.get("source_id"),
            "confidence": candidate.get("confidence"),
            "reason": candidate.get("reason"),
        }
        extracted = _extract_scenarios(candidate.get("text") or "", source)
        if extracted and not any(s.get("source_id") == source["source_id"] for s in used_sources):
            used_sources.append(source)
        for item in extracted:
            key = re.sub(r"\W+", " ", item["title"]).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            scenarios.append(item)
            if len(scenarios) >= max_scenarios:
                break

    for idx, scenario in enumerate(scenarios, 1):
        scenario["scenario_id"] = f"QA-UAT-{idx:03d}"
        for step_idx, step in enumerate(scenario["steps"], 1):
            step["step_id"] = f"{scenario['scenario_id']}-S{step_idx:02d}"
    return scenarios, used_sources


def _extract_scenarios(text: str, source: dict[str, Any]) -> list[dict[str, Any]]:
    text = text or ""
    extracted = _extract_numbered_plan_items(text, source)
    if extracted:
        return extracted
    return _extract_bullet_or_keyword_items(text, source)


def _extract_numbered_plan_items(text: str, source: dict[str, Any]) -> list[dict[str, Any]]:
    pattern = re.compile(
        r"(?im)^\s*(?:[-*]\s*)?(?P<label>P\d{1,3}|Caso\s+\d{1,3}|CP\d{1,3}|TC\d{1,3})"
        r"\s*[:.)-]\s*(?P<body>.+?)(?=^\s*(?:[-*]\s*)?(?:P\d{1,3}|Caso\s+\d{1,3}|CP\d{1,3}|TC\d{1,3})\s*[:.)-]|\Z)",
        re.DOTALL | re.MULTILINE,
    )
    out: list[dict[str, Any]] = []
    for match in pattern.finditer(text):
        label = match.group("label").strip()
        body = _clean_block(match.group("body"))
        if not body:
            continue
        out.append(_scenario_from_text(label, body, source))
    return out


def _extract_bullet_or_keyword_items(text: str, source: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        clean = line.strip()
        if len(clean) < 12 or len(clean) > 700:
            continue
        if not _looks_like_test_step(clean):
            continue
        clean = re.sub(r"^[-*]\s*", "", clean)
        clean = re.sub(r"^\d+[\).:-]\s*", "", clean)
        out.append(_scenario_from_text(None, clean, source))
    return out


def _scenario_from_text(label: str | None, body: str, source: dict[str, Any]) -> dict[str, Any]:
    title = _first_sentence(body)
    data_req = _extract_field(body, ("datos", "dato", "precondicion", "precondiciones"))
    expected = _extract_field(body, ("esperado", "resultado esperado", "validacion"))
    if not expected:
        expected = f"Se cumple lo indicado por el plan: {title}"
    steps = _split_steps(body)
    return {
        "scenario_id": "",
        "source": source,
        "source_label": label,
        "title": title[:180],
        "data_requirements": data_req,
        "steps": [{"step_id": "", "instruction": step} for step in steps],
        "assertions": [expected],
        "allowed_actions": _suggest_allowed_actions(body),
        "requires_plan_review": False,
    }


def _blocked_plan_review_scenario() -> dict[str, Any]:
    return {
        "scenario_id": "QA-UAT-001",
        "source": {
            "kind": "none",
            "title": "Sin plan de pruebas detectable",
            "source_id": "none",
            "confidence": 0,
            "reason": "no se detectaron escenarios verificables",
        },
        "source_label": None,
        "title": "Revisar manualmente el plan antes de navegar",
        "data_requirements": None,
        "steps": [
            {
                "step_id": "QA-UAT-001-S01",
                "instruction": "Detener el run y pedir al operador un plan de pruebas verificable.",
            }
        ],
        "assertions": ["No se ejecuta navegacion sin plan de pruebas."],
        "allowed_actions": [],
        "requires_plan_review": True,
    }


def _split_steps(body: str) -> list[str]:
    lines = [
        re.sub(r"^\s*(?:[-*]|\d+[\).:-])\s*", "", line).strip()
        for line in body.splitlines()
        if line.strip()
    ]
    step_lines = [
        line for line in lines
        if _looks_like_test_step(line) or line.lower().startswith(("ingresar", "abrir", "seleccionar", "buscar"))
    ]
    if step_lines:
        return step_lines[:8]
    return [_first_sentence(body)]


def _suggest_allowed_actions(text: str) -> list[str]:
    lower = text.lower()
    actions: list[str] = ["observe_visible_state"]
    if any(word in lower for word in ("abrir", "navegar", "ingresar a", "ir a")):
        actions.append("navigate_within_allowed_origin")
    if any(word in lower for word in ("click", "presionar", "seleccionar", "boton", "solapa")):
        actions.append("click_named_control")
    if any(word in lower for word in ("ingresar", "cargar", "completar", "escribir", "tipear")):
        actions.append("type_into_named_field")
    if any(word in lower for word in ("buscar", "filtrar", "consultar")):
        actions.append("use_named_search_or_filter")
    return actions


def _looks_like_test_step(line: str) -> bool:
    lower = line.lower()
    if re.match(r"^(p\d{1,3}|caso\s+\d{1,3}|cp\d{1,3}|tc\d{1,3})\b", lower):
        return True
    return any(
        word in lower
        for word in (
            "validar",
            "verificar",
            "debe",
            "mostrar",
            "cuando",
            "entonces",
            "ingresar",
            "abrir",
            "buscar",
            "seleccionar",
            "resultado esperado",
        )
    )


def _extract_field(text: str, names: tuple[str, ...]) -> str | None:
    for name in names:
        pattern = re.compile(rf"(?im)^\s*{re.escape(name)}\s*[:\-]\s*(.+)$")
        match = pattern.search(text)
        if match:
            return match.group(1).strip()
    return None


def _first_sentence(text: str) -> str:
    clean = _clean_block(text)
    if not clean:
        return "Validar escenario del plan"
    first = re.split(r"(?<=[.!?])\s+", clean, maxsplit=1)[0]
    return first[:220].strip(" -")


def _clean_block(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = (
        text.replace("&nbsp;", " ")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&amp;", "&")
    )
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _origin(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}"


def _hash_for_comment(spec: dict[str, Any], result: dict[str, Any]) -> str:
    raw = json.dumps(
        {
            "ticket": spec.get("ticket"),
            "scenarios": result.get("scenarios"),
            "verdict": result.get("verdict"),
            "summary": result.get("summary"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _utcnow() -> str:
    return datetime.utcnow().isoformat() + "Z"
