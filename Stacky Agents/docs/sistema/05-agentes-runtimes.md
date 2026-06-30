# 05 — Agentes y Runtimes

← [INDEX](INDEX.md) · hermanos: [04-api](04-api.md) · [08-configuracion-flags](08-configuracion-flags.md) · [06-servicios-daemons](06-servicios-daemons.md)

## Registry de agentes (`backend/agents/__init__.py`)
`registry: dict[str, BaseAgent]` indexado por `.type`. [V: agents/__init__.py:10-22]
| type | Clase | Nota |
|------|-------|------|
| business | BusinessAgent | brief/conversación → Épica HTML con bloques RF-XXX [V: agents/business.py:4-25] |
| functional | FunctionalAgent | análisis funcional |
| technical | TechnicalAgent | traducción funcional→técnico |
| developer | DeveloperAgent | implementación |
| qa | QAAgent | QA/UAT |
| debug | DebugAgent (FA-29) | debugging |
| pr_review | PRReviewAgent (FA-28) | revisión de PR |
| custom | CustomAgent | agentes custom de VS Code/Copilot |
`list_agents()` → `[a.describe()]`; `get(type)` → agente o None. [V: agents/__init__.py:25-30]

## BaseAgent — composición del prompt (`agents/base.py`)
`compose_system_prompt(run_ctx)` arma el system prompt aplicando, en orden: override (FA-50), few-shot (FA-12),
anti-patterns (FA-11), decisiones (FA-13), constraints (FA-08), style memory (FA-10), Stacky Skills (H4.3).
Todo con try/except defensivo: un injector que falla no rompe el run. [V: agents/base.py:56-187]
`run()` compone prompt y system prompt, y llama `copilot_bridge.invoke(...)` (camino `github_copilot`). [V: agents/base.py:192-234]
`RunContext` transporta: ticket_id, project, stacky_project_name, workspace_root, bridge_port, model_override,
system_prompt_override, flags de few-shot/anti-patterns/decisions, delta_prefix, started_by. [V: agents/base.py:17-32]

## Prompts canónicos (`backend/Stacky/agents`)
La fuente versionada de los `.agent.md` es `Stacky/agents`. `manifest.json` los lista con checksum SHA256. [V: Stacky/agents/manifest.json:6-57]
- BusinessAgent.agent.md, Developer.agent.md, FunctionalAnalyst.agent.md, QAUat1.agent.md, TechnicalAnalyst.v2.agent.md. [V: manifest.json:6-56]
- En boot, `materialize_agents()` refresca `manifest.json` desde el canonical (NO copia desde GitHub Copilot/VS Code). [V: app.py:196-217]
- `VSCODE_PROMPTS_DIR` y `agents_dir` de proyecto se ignoran (con WARNING) si difieren del canonical; `STACKY_ALLOW_VSCODE_PROMPTS_OVERRIDE` ya no habilita fuentes legacy. [V: config.py:97-122]
- Los `.agent.md` están gitignored ⇒ la DB (`agent_prompt_versions`) es el único historial auditable. [V: models.py:459-465]

## Runtimes y despacho (`agent_runner.run_agent`)
El operador elige `runtime` (default `github_copilot`). El despacho está en `agent_runner.py`. [V: agent_runner.py:94,210-366]

| runtime | Camino | Runner |
|---------|--------|--------|
| `github_copilot` (o ausente) | flujo estándar en thread, `copilot_bridge` + LLM router | agent_runner._run_in_background [V: agent_runner.py:366-369] |
| `codex_cli` | Codex CLI runner; requiere `vscode_agent_filename` | services/codex_cli_runner.start_codex_cli_run [V: agent_runner.py:218-271] |
| `claude_code_cli` | Claude Code CLI runner | services/claude_code_cli_runner.start_claude_code_cli_run [V: agent_runner.py:293-345] |

Los runners CLI crean su propia fila de ejecución; la fila original se marca `cancelled` con `replaced_by=<new_id>` para no dejar huérfanas. [V: agent_runner.py:257-271, 331-345]

### Regla de NO-fallback (invariante)
Si elegís `codex_cli` o `claude_code_cli` y el runner falla (CLI no instalado, error de arranque, lo que sea),
la ejecución se marca **error real** — NUNCA cae a `github_copilot`. [V: agent_runner.py:272-291, 346-364]
> Contexto operativo: en la práctica el síntoma "ejecuta abre Copilot / solo Haiku" fue un default que caía en
> `github_copilot`, ya resuelto: default→`claude_code_cli` + migración v1→v2. [INF: MEMORY vscode-opens-on-launch-is-copilot-path]

## LLM router y cap de modelos (`services/llm_router.py`)
- `clamp_model(model, allow_opus=False)` es la **única** función que decide qué está capado. [V: llm_router.py:35-54]
  - Cap duro `CLAUDE_CAP_MODEL="claude-sonnet-4-6"`; tiers prohibidos `("opus","fable")` se mapean al cap. [V: llm_router.py:27-30]
  - **Excepción**: con `allow_opus=True` y `model in _OPUS_ALLOWLIST={"claude-opus-4-8"}` se permite Opus. Lo usa SOLO el flujo brief→épica. fable y otros Opus siguen capados. [V: llm_router.py:31-53; agents.py:588-591]
- `decide(...)` elige modelo por agente + complejidad + backend (anthropic/copilot/vscode_bridge/mock), aplicando `clamp_model` como última línea de defensa. [V: llm_router.py:183-297]
- Defaults Claude por agente: business/functional/technical/developer = sonnet-4-6, qa = haiku-4-5. [V: llm_router.py:135-141]
- `LLM_BACKEND` (config) gobierna el catálogo de modelos: `vscode_bridge` (default config), `copilot`, `mock`, anthropic. Si la auth de Copilot falla, la lista queda vacía → sin fallback (se levanta error). [V: llm_router.py:107-118,144-156; config.py:75]
- `STACKY_DIFFICULTY_ROUTING_ENABLED` aplica downgrade(S)/upgrade(L/XL) dentro del clamp. [V: llm_router.py:272-296; config.py:497-499]

## Configuración del runtime Claude Code CLI (config.py)
`CLAUDE_CODE_CLI_MODEL` default `claude-sonnet-4-6`; `CLAUDE_CODE_CLI_EFFORT` default `medium`; `CLAUDE_CODE_CLI_TIMEOUT` default 1800s (finito, evita zombies); `CLAUDE_CODE_CLI_SKIP_PERMISSIONS` default true (corre sin prompts). [V: config.py:151-178]
→ Catálogo completo de flags del CLI en [08-configuracion-flags](08-configuracion-flags.md).
