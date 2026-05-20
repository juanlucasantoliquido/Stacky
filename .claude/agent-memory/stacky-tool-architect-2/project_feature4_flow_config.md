---
name: project-feature4-flow-config
description: Estado de implementación Feature #4 FlowConfig — mapping ado_state→agent_type determinístico
metadata:
  type: project
---

Feature #4 FlowConfig — estado al 2026-05-19.

**Fase 4.A (backend) completada.**

Archivos creados:
- `backend/services/flow_config_store.py` — store con CRUD, excepciones de dominio, fallback JSON corrupto (R4 SDD)
- `backend/api/flow_config.py` — Blueprint Flask `/flow-config` con 5 endpoints
- `backend/data/flow_config.json` — pre-poblado con 4 reglas iniciales (New→business, Active→developer, Code Review→qa, Resolved→qa)
- `backend/tests/test_flow_config.py` — 26 tests, todos PASS

Modificado:
- `backend/api/__init__.py` — registra `flow_config_bp`

**Decisiones consolidadas (DO del SDD):**
- DO-4.1: clave del mapping es `agent_type` (NO `agent_filename`). El SDD original decía `agent_filename`; el usuario lo corrigió.
- DO-4.4: pre-popular con reglas derivadas de DEFAULT_NEXT de next_agent.py

**VALID_AGENT_TYPES** en store: business, functional, technical, developer, qa — sincronizados con DEFAULT_NEXT de next_agent.py.

**Feature #4 COMPLETA — commits:**
- 4.A backend: a456c44
- 4.B frontend FlowConfigPage: 5c4b77a
- 4.C frontend TicketBoard/PipelineStatus: 695e1dd
- 4.D backend deprecaciones: c3a57b4

**Detalles 4.C:**
- TicketBoard.tsx: carga FlowConfig.list() una vez en raíz con useQuery (queryKey: flow-config, staleTime 5 min).
  Construye flowConfigMap (Map<ado_state, agent_type>) con useMemo.
  Pasa flowConfigMap por props a EpicGroup y TicketCard.
  TicketCard resuelve nextSuggested desde flowConfigMap (no desde result?.next_suggested).
  Reglas #7/#8 preservadas: Tasks/Epics con business en el map → null (no redirige a functional).
  Tooltip CA-4.3: "No hay agente configurado para el estado '<X>'. Configurá el flujo en la pestaña Config de Flujo."
- PipelineStatus.tsx: isNext eliminado (no colorea chip por next_suggested). Sección "Próximo:" eliminada del meta.
  Tipo next_suggested intacto en types.ts y en el resultado backend (rollback friendly).
- NextAgentSuggestion.tsx: deprecado en docstring. Sigue activo en OutputPanel.tsx (post-aprobación Markov).

**Detalles 4.D:**
- next_agent.py: DEPRECATED en docstring. Sigue en uso por endpoint y OutputPanel.
- agents.py GET /next-suggestion: docstring DEPRECATED + headers Deprecation:true y Sunset en response.
- ado_pipeline_inference.py: nota NOTA Feature #4 en docstring explicando que next_suggested ya no es consumido por TicketBoard.
  El campo permanece en el resultado para rollback y para TicketGraphView.jsx (visualización de chips de progreso).

**Grep next_suggested post-4.C/4.D:**
- TicketBoard.tsx: 0 referencias.
- PipelineStatus.tsx: solo en comentarios explicativos.
- TicketGraphView.jsx: usa next_suggested para colorear chips de progreso visual (NO botón Run Sugerido — fuera de scope per SDD).
- types.ts: solo en definición de tipo (rollback compat).

**Why:** Reemplaza inferencia LLM probabilística por mapping explícito operador-configurable.
**How to apply:** Al implementar 4.B/4.C verificar que el campo del body y response es `agent_type`, no `agent_filename`.
