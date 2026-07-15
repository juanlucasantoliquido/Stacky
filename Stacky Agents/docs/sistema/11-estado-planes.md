# 11 — Estado de los planes (docs/19_*..143_*)

← [INDEX](INDEX.md) · hermanos: [08-configuracion-flags](08-configuracion-flags.md) · [05-agentes-runtimes](05-agentes-runtimes.md) · [12-devops](12-devops.md) · [14-db-compare](14-db-compare.md)

Resumen de 1-2 líneas por documento. "Estado" sale del propio header del doc [V], o se deduce de git/MEMORY [INF].
NO copia el contenido de los planes — abrí `docs/<n>_*.md` para el detalle. Donde el header dice "propuesto"
pero MEMORY/git indican que se implementó, se marca el conflicto.
La numeración de planes hoy llega a 143 (`docs/NN_PLAN_*.md`); el detalle 19-46 va abajo y el addendum 47-143 al final.

| Doc | Tema | Estado | Conf. |
|-----|------|--------|-------|
| 19 | Plan de incidencias 2026-06-04 | Plan de trabajo (incidencias) | [V: header] |
| 20 | Incidente ADO-241: detección de pending-task.json | Incidente/SSD | [V: header] |
| 21 | Hardening arnés multi-proveedor (H0-H8) | IMPLEMENTADO salvo H2.5 | [INF: citado así en headers de 22-32] |
| 22 | Arnés ventaja competitiva (V0-V2) | V0 implementado; V1-V2 parciales/propuestos | [V: header 22 + cross-refs] |
| 23 | Capa perceptible | Header dice "propuesto"; **MEMORY: implementado end-to-end** (U1.5 cerrado 2026-06-13) | [V: header] / [INF: MEMORY plan-23] — conflicto, gana MEMORY/código |
| 24 | Capa amplificación operador (C0-C2) | PROPUESTO | [V: header] |
| 25 | Checklist: portar runtime nuevo | Checklist (referencia) | [V: header] |
| 26 | Memoria configurable y directivas | Header "propuesto"; **MEMORY: IMPLEMENTADO COMPLETO 2026-06-14** | [V: header] / [INF: MEMORY plan-26-27] — conflicto |
| 27 | Mejoras invisibles del motor (I0-I3) | Header "propuesto"; **implementado salvo I2.2 diferido** | [INF: cross-ref en 30-32] |
| 28 | Mejoras alto impacto invisibles (lifecycle/zombies) | IMPLEMENTADO COMPLETO 2026-06-14 (52 tests) | [V: header 28] |
| 29 | Calidad del resultado a la primera | IMPLEMENTADO COMPLETO 2026-06-15 (Q0.1-Q2.2; Q2.1 diferido) | [V: header 29] |
| 30 | Integridad verificada contra la realidad | PROPUESTO (flags G* declarados, default OFF) | [V: header 30; config.py:643-682] |
| 31 | Verificación ejecutable del entregable | PROPUESTO (flags E* declarados OFF) | [V: header 31; config.py:339-379] |
| 32 | Contrato de aceptación ejecutable | PROPUESTO (flags A* declarados OFF) | [V: header 32; config.py:381-417] |
| 33 | Flags 100% configurables por UI | IMPLEMENTADO | [V: header 33] |
| 34 | Client profile efectivo y sin fricción | PROPUESTO | [V: header 34] |
| 35 | Aprendizaje del arnés (patrones reutilizables) | PROPUESTO | [V: header 35] |
| 36 | Selector de runtime sin fallback silencioso | Header PROPUESTO; **el flag `STACKY_RUNTIME_STRICT` y el dispatch sin fallback existen en código** | [V: header 36] / [V: config.py:684-690; agent_runner.py:272-364] — implementado en lo esencial |
| 37 | Claude CLI auth real sin degradar a Copilot | Header PROPUESTO; **MEMORY: RESUELTO 2026-06-17 (commit cb0badde)** default→claude_code_cli + timeout finito | [V: header] / [INF: MEMORY vscode-opens; config.py:164] — conflicto |
| 38 | Versión visible, épica desde brief, trazabilidad | Header PROPUESTO; **MEMORY: IMPLEMENTADO COMPLETO 2026-06-17** | [V: header] / [INF: MEMORY plan-38; config.py:692-722] — conflicto |
| 39 | Historial de runs + fix épica CLI + DB read-only | Header PROPUESTO; **MEMORY: IMPLEMENTADO 2026-06-17** (flags en config) | [V: header] / [INF: MEMORY plan-39; config.py:419-428] — conflicto |
| 40 | Business Agent: épica genérica autónoma + modelo | PROPUESTO v2 (F3 wiring pendiente; BusinessAgent ya v1.1.0) | [V: header 40] / [INF: MEMORY plan-40] |
| 41 | Pre-vuelo de intención y plan negociable | Header PROPUESTO; **autopublish backend SÍ existe** (`STACKY_EPIC_AUTOPUBLISH_BACKEND`) | [V: header 41] / [V: config.py:699-704] |
| 42 | Épicas grounded en docs + selector modelo CLI | v3 PROPUESTO (no implementado); selector roto en frontend; run-brief ya lee model/effort | [V: header 42] / [V: agents.py:584-598] |
| 43 | Generador épicas config-auto + selector modelo/effort | PROPUESTO; **F0/F1 parcial en código** (efforts oficiales + allow_opus en run-brief) | [V: header 43] / [V: agents.py:588-597; llm_router.py:31-32] |
| 44 | Observatorio de grounding + sugeridor de diccionario | PROPUESTO (ningún ítem implementado) | [V: header 44] |
| 45 | Catálogo de procesos en UI + soporte de issues | PROPUESTO | [V: header 45] |
| 46 | Panel de salud operativa (triage solo-lectura) | PROPUESTO (no implementado) | [V: header 46] |

## Lectura del patrón
- Los planes con flags en `config.py` (30, 31, 32, 36, 38, 39, 41, 43) tienen al menos el andamiaje declarado;
  el "estado" del header suele ir por detrás del código real porque los flags nacen OFF antes de implementarse el comportamiento. [INF: comparación headers vs config.py]
- Cuando el header dice "propuesto" pero MEMORY/commits dicen "implementado/desplegado", **gana el código**;
  esos casos están marcados como conflicto arriba (23, 26, 36, 37, 38, 39). [V: regla R: código > doc legada]
- Para el estado exacto y verificable de un plan, hay que auditar sus flags + tests, no solo el header. [NV: no se corrieron tests en esta reconstrucción]

## Addendum: planes 47-143 (por evidencia en la rama `plans-138-141-serie-ux-ui`)
"En código" = hay blueprint/servicio/flag presente en esta rama (no significa exhaustivamente probado).
| Rango / plan | Tema | ¿En código en esta rama? | Conf. |
|--------------|------|--------------------------|-------|
| 47-71 | Serie larga (dedup, GitLab tracker, RAG catalog, MCP…) | No auditado plan-por-plan aquí | [NV] |
| 72-116 | **Suite DevOps** (CI, pipelines, migrador, servidores, doctores, consola remota) | Sí: blueprints `devops*`/`ci`/`migrator`/`pipeline-generator` + servicios `gitlab_*`/`pipeline_*`/`migrator_*`/`remote_exec` | [V: api/__init__.py:42-111] → [12-devops](12-devops.md) |
| 106/127 | Modelo local (Qwen/Ollama) + reuso IA local | Sí: blueprint `/api/llm` | [V: __init__.py:54,110] |
| 109-115 | **Docs/RAG/grafo documental** | Sí: `doc_graph`, `docs_rag`, `rag_retriever`, endpoints `/api/docs/graph`, `/api/docs-rag` | [V: docs.py:210; config.py:511-539] → [13-docs-rag-grafo](13-docs-rag-grafo.md) |
| 110 | Revisor de PRs (Haiku + modelo local) | Sí: blueprint `/api/pr-review` (`STACKY_PR_REVIEWER_ENABLED` true) | [V: __init__.py:55; config.py:121] |
| 117 | Insights locales de ejecuciones | Flags presentes | [V: tests test_plan117_insights_flags.py en git status] |
| 119 | Rediseño minimalista dashboard DevOps | En código (flag UI_V2) | [INF: MEMORY plan-119-status] |
| 120 | Centro de Despliegues + rollback 1-click | **No** en esta rama (otra rama sin mergear) | [V: grep negativo deploy/rollback] |
| 121 | Centinela egreso secretos/PII | Servicio `egress_policies`/`pii_masker` en runner | [V: agent_runner.py:22] |
| 122-126 | **DB Compare** | Sí: blueprint `/api/db-compare` + `dbcompare_*` | [V: db_compare.py:24] → [14-db-compare](14-db-compare.md) |
| 128 | Tablero Evolución de Planes | No confirmado en esta rama | [NV] |
| 129/130/131 | Paleta global / Gate integridad código / Resolutor incidencias | **No** como blueprint/servicio en esta rama | [V: grep negativo code-integrity/IncidentAnalyst] |
| 132 | Consola desde ejecuciones activas | Parcial: `CodexConsoleDock`/`ActiveRunsPanel` en SPA | [INF: App.tsx:23-24; ver 07-frontend] |
| 133-137 | Contrato contexto / awareness / errores mudos / protección UI / Documentador v2 | Parcial/WIP (p.ej. `LoadErrorState.tsx`, `loadError.ts` sin commitear; endpoints documenter existen) | [V: git status untracked; docs.py:267-347] / [INF: MEMORY] |
| 138-143 | Sistema de diseño v2 / App Shell / estados / tema / costos / motion | Solo docs de plan en esta rama; implementación pendiente | [V: git log docs(plan-138..141)] / [INF: MEMORY serie-ux-ui-138-141] |
> Regla anti-alucinación: "No en esta rama" se afirma tras grep negativo real; los planes no auditados quedan [NV], no "no existe".
