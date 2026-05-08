---
name: Stacky — stack y arquitectura
description: Resumen del ecosistema Stacky (pipeline de agentes en VS Code Copilot Chat) para tener contexto rápido en próximas tareas.
type: project
---

Stacky es un pipeline de automatización que orquesta agentes de Copilot Chat en VS Code (PM, DEV, QA, DOC, DBA, TL) para procesar tickets de Azure DevOps de forma autónoma. Vive en `Tools/Stacky/`.

**Why:** El usuario desarrolla automatizaciones que invocan agentes de IA en VS Code. Stacky es el corazón de ese ecosistema: scrape de tickets → invoke PM → detect completion via flags → invoke DEV → QA → DOC, con reintentos, rework y observabilidad.

**How to apply:** Cuando haya tareas sobre Stacky:
- Los stages canónicos del pipeline son: `pm`, `pm_revision`, `dev`, `dev_rework`, `tester`, `doc`, `dba`, `tl`.
- La comunicación con VS Code es via `copilot_bridge.py` (HTTP a localhost:5051 preferido, UI automation fallback).
- Los agentes señalizan finalización escribiendo flags (`PM_COMPLETADO.flag`, `DEV_COMPLETADO.md`, etc.) en la carpeta del ticket.
- El dashboard Flask (`dashboard_server.py` + `dashboard.html`) vive en :5050, con features del usuario como Rally (grid de largada) y Sync.
- El estado vive en `pipeline/state.json`; las métricas por proyecto en `knowledge/<PROJECT>/metrics.json`.
- F1-F4 añadió 6 módulos de observabilidad: `action_tracker`, `pipeline_events` (JSONL+SSE), `error_classifier`, `sse_bus`, `ticket_scoring`, `estimation_store`.
- Los 8 stages mapean a `phase` canónica del evento: pm→pm, pm_revision→pm, dev→dev, dev_rework→dev, tester→tester, doc→other, dba→dba, tl→tl.
