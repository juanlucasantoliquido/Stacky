# Plan de Robustecimiento del Arnés — Stacky Agents

Fecha: 2026-06-09 · Branch base: `feat/memoria-colaborativa-hardening`
Principio rector: **maximizar valor agregado vs. "Claude pelado" sin agregar fricción al operador**. Todo lo propuesto es transparente: el operador sigue apretando "Run" sobre un ticket.

---

## 1. Diagnóstico basado en evidencia

### 1.1 Arquitectura actual (verificada en código)

Dos runtimes con pipelines **asimétricos**:

**Runtime `github_copilot`** (`backend/agent_runner.py:483-819`) — pipeline completo:
enriquecimiento de contexto → PII masking → output cache (FA-31) → LLM router (FA-04) → egress policies (FA-41) → composición de system prompt con few-shot (FA-12), anti-patterns (FA-11), decisiones (FA-13), constraints (FA-08), style memory (FA-10) (`agents/base.py:56-159`) → **contract validator** (`agent_runner.py:688`) → **confidence scoring** (`agent_runner.py:696`) → cache store → webhooks → audit chain → embeddings index → post_run_memory.

**Runtime `claude_code_cli`** (`services/claude_code_cli_runner.py:257-696`) — pipeline mínimo:
enriquecimiento de contexto (`:332`) → PII masking (`:352`) → spawn de `claude -p --input-format stream-json` con `--append-system-prompt-file` que referencia el `.agent.md` (`:703-753`, `:853-872`) → stream de eventos → post_run_memory (`:584`). **Y nada más.**

### 1.2 Brechas concretas

| # | Brecha | Evidencia |
|---|--------|-----------|
| B1 | **El runtime más capaz (Claude Code CLI, el único realmente agéntico) es el que menos arnés tiene.** Sin contract validator, sin confidence, sin cache, sin few-shot/anti-patterns/decisiones/constraints/style memory, sin egress check, sin audit chain, sin embeddings. | `claude_code_cli_runner.py` no importa `contract_validator`, `confidence`, `output_cache`, `few_shot`, `anti_patterns`, `decisions`, `constraints`, `egress_policies`, `audit_chain`, `embeddings` (grep negativo). `agent_runner.py:686-757` solo corre en el path copilot. |
| B2 | **Telemetría nativa del CLI descartada.** El evento `result` de stream-json trae `session_id`, `usage` (tokens), `total_cost_usd`, `num_turns` — nada de eso se parsea ni persiste. Sin `session_id` no hay `--resume` (re-runs arrancan en frío). | Grep de `usage\|cost\|session_id` en `claude_code_cli_runner.py` → 0 hits. `_parse_claude_code_line` (`:972`) solo extrae texto. |
| B3 | **Outputs por convención de archivos, validados tarde y post-hoc.** El contrato comment.html / pending-task.json vive como texto en `_STACKY_RULES` (`claude_code_cli_runner.py:821-838`); la validación la hace `output_watcher.py` poleando disco DESPUÉS de que el agente terminó. Causa raíz ya confirmada de "crea archivos pero no la task": JSON inválido + mismatch ordinal vs ADO id. El agente nunca recibe feedback para autocorregirse. | `output_watcher.py:1-35` (es fallback), `agent_completion.py` (gateway en shadow). |
| B4 | **Cero apalancamiento de capacidades nativas de Claude Code**: no se generan hooks (`settings.json`), ni skills, ni CLAUDE.md por workspace, ni allowlist de herramientas (se usa `acceptEdits` o `--dangerously-skip-permissions`, `:743-748`), ni servidores MCP. Stacky compite contra "Claude pelado" usando solo un system prompt + un mensaje. | `_build_command` (`:703-753`) — únicos flags: print/stream/system-prompt/permissions/model. |
| B5 | **Sin retries ni autocorrección.** `stdin` queda abierto para el operador (`:439-448`) pero Stacky nunca lo usa para devolver errores de validación al agente. Un exit code ≠ 0 o un artifact inválido termina en `error` y el operador re-lanza a mano desde cero. | `:559-650` — solo dos ramas terminales. |
| B6 | **Memoria colaborativa lista pero apagada y con doble canal.** `_inject_stacky_memory_block` (`context_enrichment.py:217`) sí corre en ambos runtimes vía `enrich_blocks`, pero flag `STACKY_MEMORY_INJECTION_ENABLED=false`; convive con FA-11/12/13 que inyectan conocimiento similar por system prompt (solo copilot) → riesgo de doble inyección al prender. | `context_enrichment.py:225`, `agents/base.py:70-139`. |
| B7 | **Sin gestión de presupuesto de contexto.** `enrich_blocks` apila épica + artifacts + similares + comentarios ADO + perfil cliente + memoria sin cap de tokens; `estimate_tokens` existe (`prompt_builder.py:62`) pero nadie lo usa para recortar. | `context_enrichment.py:34-99`. |
| B8 | **Evals casi inexistentes.** `backend/evals/` solo cubre `pm_intelligence` y `ticket_diagnostics`. Editar un `.agent.md` no tiene gate de regresión: el primer test es producción. | `ls backend/evals`. |
| B9 | **Router de modelos no aplica al CLI.** `llm_router` decide modelo solo en el path copilot; el CLI usa `model_override` o config estática (`:725`). | `agent_runner.py:627` vs `claude_code_cli_runner.py:703`. |

### 1.3 Qué ya está bien (no tocar / preservar)

- Heartbeat + reaper + manifest por run (`claude_code_cli_runner.py:450-471`, `manifest_watcher`).
- PII mask/unmask simétrico en ambos runtimes.
- Regla "sin fallback silencioso entre runtimes" (`agent_runner.py:114-121`).
- `output_watcher` como red de seguridad (degradarlo a fallback, no eliminarlo).
- Log streaming en vivo + consola interactiva in-page (stdin abierto) — es la base de F1.3.

---

## 2. Propuestas priorizadas

Criterio: impacto en (efectividad × confiabilidad × costo) ÷ esfuerzo, con transparencia obligatoria.

### FASE 1 — Paridad y autocorrección (alto impacto / bajo esfuerzo, ~1-2 semanas)

**F1.1 — Paridad de calidad en `claude_code_cli`** (B1)
Antes de `_mark_terminal(completed)` en el CLI runner, correr `contract_validator.validate(agent_type, output)` y `confidence.score(output)`; persistir en `contract_result` y `metadata` igual que el path copilot. Si el contrato falla con errores duros → status `needs_review` (estado ya soportado por `agent_completion.py`), no `completed`.
- Esfuerzo: bajo (módulos ya existen, es cablear ~30 líneas en `claude_code_cli_runner.py:559`).
- Transparencia: total — el operador solo ve un badge de score que ya existe en la UI para copilot.

**F1.2 — Capturar telemetría nativa del stream** (B2)
En `_parse_claude_code_line` / `_read_stream`, capturar el evento `result`: `session_id`, `usage.input_tokens/output_tokens/cache_read_input_tokens`, `total_cost_usd`, `num_turns`, `is_error`. Persistir en `metadata_dict`. Esto habilita: dashboard de costo real por agente/ticket, detección de runs anómalos (num_turns explosivo), y F2.3 (resume).
- Esfuerzo: bajo. Transparencia: total (solo metadata).

**F1.3 — Loop de autocorrección sobre stdin** (B3, B5)
Al detectar fin de turno del agente (evento `result` parcial o quiescencia), validar sincrónicamente los artifacts esperados (`Agentes/outputs/<ADO_ID>/comment.html`, `epic-<ADO_ID>/*/pending-task.json`): JSON parseable, schema (campos requeridos, **ADO id real vs ordinal**), HTML no vacío. Si falla → escribir UN mensaje correctivo por el stdin ya abierto (`_user_message_line`, `:199`) con el error exacto, máx 1-2 reintentos, y loguearlo en el stream. Recién después cerrar.
- Ataca en origen la causa raíz #1 confirmada ("crea archivos pero no la task").
- Esfuerzo: medio (validador de schema nuevo + máquina de estados simple).
- Transparencia: total — el operador ve en la consola "Stacky detectó pending-task.json inválido, pidiendo corrección…" y el run termina bien en vez de necesitar re-lanzamiento manual. Cap de reintentos para no quemar tokens.

**F1.4 — Hooks de Claude Code generados por Stacky** (B3, B4)
Generar por run un `settings.json` efímero (en `run_dir`) pasado vía `--settings`: hook `PostToolUse` sobre `Write|Edit` que, si el path matchea `Agentes/outputs/**/pending-task.json`, ejecuta un script de validación (puede llamar a un endpoint local `POST /api/agents/validate-artifact`) y devuelve el error al agente **en el momento de la escritura**. Complementa F1.3 (defensa en profundidad: hook = inmediato; F1.3 = al cierre; output_watcher = fallback).
- Esfuerzo: medio-bajo. Transparencia: total, cero config del operador (Stacky genera y limpia el archivo).

### FASE 2 — Valor diferencial vs. Claude pelado (~2-4 semanas)

**F2.1 — Stacky MCP server** (B3, B4) — *la propuesta de mayor valor agregado*
Servidor MCP stdio mínimo inyectado vía `--mcp-config` en `_build_command`, con 4-6 tools:
- `stacky_get_ticket(ado_id)` — ticket + épica + comentarios (reemplaza parte del prompt gigante por retrieval bajo demanda → menos tokens, contexto siempre fresco).
- `stacky_search_memory(query)` — memoria colaborativa on-demand (complementa la inyección estática; resuelve la tensión de B6: inyectar poco, dejar que el agente pida más).
- `stacky_search_similar(query)` — embeddings de ejecuciones pasadas (FA-01, hoy solo indexa copilot).
- `stacky_submit_comment(ado_id, html)` / `stacky_submit_task(epic_ado_id, payload)` — **reemplazan la convención de archivos por tool calls con schema validado server-side**: imposible entregar JSON inválido o id mismatcheado; Stacky encola en su outbox ADO existente (`ado_write_outbox`). La regla "solo Stacky escribe en ADO" se mantiene intacta — el MCP server ES Stacky.
- Mantener file-drop + output_watcher como fallback durante transición (flag por proyecto).
- Esfuerzo: medio (FastMCP/SDK Python; la lógica de negocio ya existe en services).
- Transparencia: total. Esto es exactamente lo que "Claude pelado" no puede tener: acceso gobernado al estado de Stacky/ADO sin credenciales en manos del agente.

**F2.2 — Conocimiento del proyecto como system prompt / skills en el CLI** (B1, B4)
Portar al CLI lo que hoy solo recibe copilot: extender `_build_system_prompt` (`:853`) con secciones compactas generadas desde `anti_patterns.relevant()`, `decisions.relevant()`, `constraints.relevant()`, `client_profile` y `glossary` (caps de tamaño, ranking por relevancia con `context_text`). Alternativa equivalente: materializar skills (`.claude/skills/`) por workspace para conocimiento estable (convenciones del cliente, formato de plan de pruebas) y dejar el system prompt para lo dinámico.
- Esfuerzo: medio-bajo (los services ya existen; es composición + caps).
- Transparencia: total. Cuidado explícito con B6: definir UN dueño por tipo de conocimiento (memoria colaborativa ≠ anti-patterns ≠ decisiones) antes de prender todo, para no duplicar tokens.

**F2.3 — Re-runs con `--resume` + delta prompt** (B2, B5)
Con `session_id` persistido (F1.2): cuando el operador re-lanza el mismo ticket+agente, ofrecer continuación de sesión (`claude --resume <session_id>`) con un delta prompt (el módulo `delta_prompt.py` ya existe para copilot) en vez de arranque en frío. Ahorro de tokens enorme (cache de contexto de sesión) y mejor calidad (el agente recuerda qué hizo).
- Esfuerzo: bajo-medio. Transparencia: el flujo de re-run de la UI no cambia; solo es más rápido y barato.

**F2.4 — Presupuesto de contexto con ranking** (B7)
En `enrich_blocks`, presupuesto total configurable (p.ej. 25k tokens estimados con `estimate_tokens`): ordenar bloques por valor (ticket > épica > memoria > similares > comentarios viejos), truncar con marcador `[recortado por presupuesto — pedir vía MCP si hace falta]`. Sinergia directa con F2.1 (lo recortado queda accesible on-demand).
- Esfuerzo: bajo. Transparencia: total; metadata registra qué se recortó.

**F2.5 — Encendido gradual de memoria colaborativa en CLI** (B6)
Prender `STACKY_MEMORY_INJECTION_ENABLED` por proyecto (no global), con dedup contra FA-* resuelto (consolidación pendiente de Fase B del plan de memoria) y métricas de hit-rate ya persistidas en el block metadata (`context_enrichment.py:262-268`). Medir 2 semanas antes de default ON.

### FASE 3 — Calidad sostenida y optimización (~3-4 semanas, incremental)

**F3.1 — Eval harness por agente con golden set** (B8)
Por cada `agent_type` activo: 3-5 tickets dorados (inputs congelados) + assertions (contract score mínimo, presencia de artifacts válidos, no-regresión de confidence). Comando `python -m evals run <agent>` y gate sugerido (no bloqueante al principio) al editar un `.agent.md`. Reusa `contract_validator` como juez barato; opcional LLM-judge con Haiku para criterios blandos.
- Transparencia: invisible al operador; protege la calidad que el operador ya espera.

**F3.2 — Routing de modelo para CLI** (B9) — **PROMOVIDO A OBLIGATORIO, ver §6.2**
La decisión completa (haiku/sonnet, cap duro sin Opus/Fable, punto único de clamp y test) está en §5.2. Con la telemetría de F1.2 se cierra el loop: costo real por decisión de routing.

**F3.3 — Score de salud del arnés (dashboard)**
Con datos que las fases 1-2 ya persisten: tasa de runs completed-sin-intervención, tasa de autocorrecciones F1.3 (si sube, el prompt/contrato necesita ajuste), costo por ticket, contract score promedio por agente, hit-rate de memoria. Una vista, sin acciones nuevas requeridas al operador.

**F3.4 — Allowlist de herramientas por tipo de agente** — **DESCARTADA como default; ver §5.3**
Decisión explícita del usuario (2026-06-09): el runtime CLI corre SIEMPRE con `--dangerously-skip-permissions`. Las allowlists `--allowedTools`/`--disallowedTools` quedan como opción futura opt-in por agente (frontmatter del `.agent.md`), nunca como default ni como bloqueo. No implementar en esta tanda.

---

## 3. Secuencia y dependencias

```
F1.2 (telemetría) ──→ F2.3 (resume) ──→ F3.2 (routing con costo real)
F1.1 (paridad validación) ──→ F3.1 (evals usan contract scores)
F1.3 (autocorrección stdin) ←→ F1.4 (hooks) ──→ F2.1 (MCP reemplaza file-drop)
F2.4 (presupuesto contexto) ←─ sinergia ─→ F2.1 (retrieval on-demand)
F2.2 + F2.5 requieren decisión previa: un dueño por tipo de conocimiento (anti doble inyección)
```

## 4. Reglas de implementación (no negociables)

1. **Cero fricción nueva**: ninguna propuesta agrega pasos, prompts de confirmación ni configuración obligatoria al operador. Todo se activa por flags de backend, por proyecto, OFF por defecto.
2. **Sin fallback silencioso entre runtimes** (regla existente, se preserva).
3. **`output_watcher` y `agent_completion` quedan como fallback**, no se eliminan hasta que F1.3/F1.4/F2.1 demuestren tasa de éxito superior en producción.
4. **Solo Stacky escribe en ADO**: F2.1 lo refuerza (el MCP server encola en el outbox de Stacky), no lo debilita.
5. **No construir RBAC**: Stacky es mono-operador; cualquier "permiso" es ergonomía/seguridad del agente (F3.4), no control de acceso humano.
6. Cada feature nueva con test dirigido en `backend/tests/` (patrón existente: `test_claude_code_cli_prompt.py`).

## 5. Decisiones del usuario (2026-06-09) — vinculantes

### 5.1 PowerShell como wrapper del CLI: **NO** (veredicto técnico)

**Pedido**: "usar Claude en un PowerShell, que será mejor y más maleable".
**Veredicto: el wrapper PowerShell empeora el arnés en todos los ejes y no agrega ninguna maleabilidad que Python no tenga ya.** Evidencia del runner actual (`services/claude_code_cli_runner.py`):

- **Spawn actual**: `subprocess.Popen` directo sobre el binario resuelto (`_resolve_claude_code_cli_bin`, `:756-801` — exe o shim npm `claude.cmd`), sin shell, con `text=True, encoding="utf-8", errors="replace", bufsize=1` (line-buffered) y `CREATE_NO_WINDOW` (`:414-434`). stdin/stdout/stderr son pipes directos al proceso de Claude: el runner escribe mensajes stream-json por stdin (`:443`) y dos threads lectores parsean JSONL de stdout/stderr (`:476-487`). Kill: `proc.terminate()/kill()` sobre el handle directo (`:187,:508-512`).
- **Qué rompería `powershell.exe -Command claude ...` como intermediario**:
  1. **Kill huérfano**: `proc.terminate()` mataría a powershell, no a `claude` (Windows no propaga señales a hijos; haría falta Job Objects o `taskkill /T`). Hoy el cancel del operador y el reaper funcionan porque el handle es el proceso real.
  2. **stderr corrupto**: PowerShell 5.1 envuelve cada línea de stderr nativo en ErrorRecords (NativeCommandError), rompiendo el reader de `claude-code-stderr` y ensuciando logs.
  3. **Encoding/buffering**: PS re-encodea el pipeline (UTF-16/`$OutputEncoding`) y bufferiza por objetos → riesgo de romper el parseo JSONL línea a línea y la latencia del streaming en vivo, que es la base de la consola in-page.
  4. **Escaping**: prompts y paths con `$`, backticks, comillas → doble capa de escaping frágil. Hoy no hay escaping porque no hay shell.
  5. **Capa extra de proceso** sin contrapartida: con shim npm ya hay una capa cmd; PS agregaría una segunda.
- **La "maleabilidad" buscada ya existe, más barata y robusta, desde Python**: env vars (`build_agent_env`, `:433`), working dir (`cwd=` del Popen), pre/post comandos (código Python antes/después del spawn), configuración por run (`settings.json` efímero vía `--settings` — F1.4), hooks de Claude Code (F1.4), CLAUDE.md/skills por workspace (F2.2), MCP (F2.1). Cualquier cosa que un wrapper PS podría hacer, el runner ya la hace o la hace una fase del plan, sin perder control del proceso.
- **Único caso donde PS sí suma** (opcional, fuera del runtime): generar en `run_dir` un script `repro.ps1` con el comando exacto + env, para que el operador reproduzca un run a mano al debuggear. Costo casi nulo; se puede colgar de F1.2.

**Acción en el plan**: ninguna migración a PowerShell. Se agrega el `repro.ps1` opcional como sub-ítem de F1.2.

### 5.2 Routing de modelos OBLIGATORIO: haiku/sonnet con cap duro (reemplaza el alcance de F3.2 y corrige `llm_router`)

**Regla dura**: tareas simples → `claude-haiku-4-5`; complejas → `claude-sonnet-4-6`; **NUNCA un modelo superior a Sonnet 4.6 (ni Opus ni Fable), en ningún runtime, ni siquiera por override del operador.**

- **Dónde se decide**: `llm_router.decide()` extendido al runtime CLI. En `claude_code_cli_runner.run`, antes de `_build_command` (`:403`), llamar a `decide(agent_type, blocks, override=model_override, fingerprint=...)` y pasar `decision.model` como `--model` (`:750-751`). Se elimina la dependencia de `config.CLAUDE_CODE_CLI_MODEL` estático como fuente primaria (queda como fallback si el router falla).
- **Criterio simple vs compleja** (reusa señales que `decide()` ya computa, `:144,:215-227`):
  - *Haiku*: agentes QA/doc/funcional con contexto enriquecido < ~6k tokens estimados; complejidad de fingerprint S/M; re-runs con `--resume` (delta corto).
  - *Sonnet*: agentes developer/PM-TL; contexto > 6k tokens; fingerprint L/XL; cualquier caso dudoso (default seguro = sonnet, no escalar).
- **Cap duro en UN solo punto**: función `clamp_model(model) -> str` en `llm_router.py` que mapea todo lo prohibido (`claude-opus-*`, `claude-fable-*`, ids desconocidos de tier superior) a `claude-sonnet-4-6`. Se aplica como última línea de `decide()` sobre TODA decisión, **incluido el override del operador** (`:193`). Corregir además las ramas existentes que hoy devuelven `claude-opus-4-7` (`:218-222` → sonnet) y quitar opus de `CLAUDE_MODELS` (`:24`).
- **Test obligatorio**: `backend/tests/test_llm_router_cap.py` — asserts: (1) fingerprint XL → sonnet, no opus; (2) `override="claude-opus-4-7"` → sonnet con reason que registre el clamp; (3) qa + contexto chico → haiku; (4) ningún valor de retorno de `decide()` matchea `opus|fable` (property-style sobre el espacio de inputs típicos).
- **Telemetría**: F1.2 persiste costo/tokens reales por decisión → dashboard F3.3 valida que el routing baja costo sin bajar contract score.

### 5.3 `--dangerously-skip-permissions` SIEMPRE activo en el runtime CLI

Decisión explícita del usuario. `CLAUDE_CODE_CLI_SKIP_PERMISSIONS` pasa a default `true`; la rama `--permission-mode acceptEdits` (`:745-748`) queda como código muerto a remover o detrás de un flag de emergencia. F3.4 (allowlists) descartada como default, reformulada como opt-in futuro por agente. **Trade-off (una línea)**: el agente puede ejecutar cualquier herramienta/comando en la máquina del operador sin confirmación; la mitigación es la validación de artifacts (F1.3/F1.4) y la regla "solo Stacky escribe en ADO" (F2.1), no permisos.

---

## 6. Resumen ejecutivo

El arnés ya hace bien la orquestación (heartbeats, logs en vivo, PII, trazabilidad), pero **el 90% de su inteligencia (validación, conocimiento del proyecto, cache, routing, audit) solo aplica al runtime copilot, mientras el runtime que realmente ejecuta trabajo agéntico (Claude Code CLI) recibe un system prompt y queda solo**. Cerrar esa asimetría (Fase 1), darle al agente acceso gobernado al estado de Stacky vía MCC/hooks en vez de convenciones de archivos frágiles (Fase 2), y proteger la calidad con evals y telemetría de costo real (Fase 3) convierte a Stacky en algo que "Claude pelado" no puede replicar: contexto curado del proyecto + herramientas validadas + autocorrección + memoria — todo invisible para el operador.
