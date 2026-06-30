# 11 — Estado de los planes (docs/19_*..46_*)

← [INDEX](INDEX.md) · hermanos: [08-configuracion-flags](08-configuracion-flags.md) · [05-agentes-runtimes](05-agentes-runtimes.md)

Resumen de 1-2 líneas por documento. "Estado" sale del propio header del doc [V], o se deduce de git/MEMORY [INF].
NO copia el contenido de los planes — abrí `docs/<n>_*.md` para el detalle. Donde el header dice "propuesto"
pero MEMORY/git indican que se implementó, se marca el conflicto.

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
