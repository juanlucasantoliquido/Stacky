# 08 — Configuración y Flags

← [INDEX](INDEX.md) · hermanos: [05-agentes-runtimes](05-agentes-runtimes.md) · [06-servicios-daemons](06-servicios-daemons.md)

Toda la config vive en `backend/config.py` (clase `Config`, instancia `config`). Carga `.env` desde
`backend_root/.env` y `cwd/.env`, más `runtime_config.json`. [V: config.py:13-16, 725]
**R5 — secretos**: los valores sensibles (PAT/tokens) se documentan como `<REDACTADO>`; nunca copiar valores reales.

## Núcleo
| Var | Default | Controla | Conf. |
|-----|---------|----------|-------|
| `PORT` | 5050 | puerto del backend | [V: config.py:55] |
| `LOG_LEVEL` | INFO | nivel de logging | [V: config.py:56] |
| `DATABASE_URL` | `sqlite:///data/stacky_agents.db` | conexión DB | [V: config.py:58-60] |
| `ALLOWED_ORIGINS` | `http://localhost:5173` | CORS | [V: config.py:65-72] |
| `STACKY_ENABLE_CORS` | false | forzar CORS | [V: config.py:73] |
| `LLM_BACKEND` | `vscode_bridge` | backend LLM (vscode_bridge/copilot/mock/anthropic) | [V: config.py:75] |
| `LLM_MODEL` | claude-sonnet-4.5 | modelo legacy | [V: config.py:76] |
| `VSCODE_BRIDGE_PORT` | 5052 | puerto del bridge VS Code | [V: config.py:93] |

## Copilot / GitHub Models
`COPILOT_MODEL` (gpt-4.1), `COPILOT_ENDPOINT`, `COPILOT_MODELS_ENDPOINT`, `COPILOT_INTEGRATION_ID` (vscode-chat). [V: config.py:79-90]

## Runtime Codex CLI
`CODEX_CLI_BIN` (codex), `CODEX_CLI_MODEL` (""), `CODEX_CLI_SANDBOX` (danger-full-access), `CODEX_CLI_APPROVAL` (never),
`CODEX_CLI_CONTRACT_GATE_ENABLED`, `CODEX_CLI_AUTOCORRECT_ENABLED`/`_MAX_RETRIES` (2), `CODEX_CLI_MODEL_DENYLIST`,
`CODEX_CLI_RESUME_ENABLED`/`_PROJECTS`. [V: config.py:124-149]

## Runtime Claude Code CLI
| Var | Default | Nota |
|-----|---------|------|
| `CLAUDE_CODE_CLI_BIN` | claude | binario |
| `CLAUDE_CODE_CLI_MODEL` | claude-sonnet-4-6 | modelo fijo (vacío = router) |
| `CLAUDE_CODE_CLI_EFFORT` | medium | `--effort` (low/medium/high) |
| `CLAUDE_CODE_CLI_TIMEOUT` | 1800 | cap de sesión finito (evita zombies); 0=ilimitado |
| `CLAUDE_CODE_CLI_PERMISSION_MODE` | acceptEdits | modo permisos |
| `CLAUDE_CODE_CLI_SKIP_PERMISSIONS` | true | `--dangerously-skip-permissions` (corre sin prompts) |
| `CLAUDE_CODE_CLI_CONTRACT_GATE_ENABLED` | false | degrada a needs_review si contrato falla (F1.1) |
| `CLAUDE_CODE_CLI_AUTOCORRECT_ENABLED`/`_MAX_RETRIES` | false / 2 | loop de autocorrección (F1.3) |
| `CLAUDE_CODE_CLI_HOOKS_ENABLED` | false | settings.json efímero con hook de validación (F1.4) |
| `CLAUDE_CODE_CLI_SYSTEM_PROMPT_MODE` | append | append vs user_message |
| `CLAUDE_CODE_CLI_PROJECT_KNOWLEDGE_ENABLED`/`_PROJECTS` | false | conocimiento del proyecto en prompt (F2.2) |
| `CLAUDE_CODE_CLI_RESUME_ENABLED`/`_PROJECTS` | false | re-runs con --resume (F2.3) |
| `CLAUDE_CODE_CLI_MCP_ENABLED`/`_PROJECTS` | false | MCP server vía --mcp-config (F2.1) |
[V: config.py:151-274]

## Modelos (cap duro) — interacción con llm_router
`CLAUDE_CAP_MODEL="claude-sonnet-4-6"`, tiers prohibidos `(opus,fable)`, allowlist Opus `{claude-opus-4-8}` solo
en brief→épica. No son env vars: son constantes en `llm_router.py`. [V: llm_router.py:27-33] Ver [05-agentes-runtimes](05-agentes-runtimes.md).

## Familias de flags `STACKY_*` (por plan; default OFF salvo nota)
- **Contexto/memoria**: `STACKY_CONTEXT_BUDGET_*`, `STACKY_CONTEXT_DEDUP_*`, `STACKY_CONTEXT_RERANK_ENABLED`, `STACKY_MEMORY_INJECTION_PROJECTS`, `STACKY_MEMORY_CAPS_JSON`, `STACKY_MEMORY_REVIEW_SWEEP_HOURS` (0), `STACKY_MEMORY_DIRECTIVE_MAX_CHARS` (4000), `STACKY_MEMORY_INJECT_SCOPES`, `STACKY_MEMORY_VALIDATOR_ADVANCED`, `STACKY_MEMORY_GIT_SYNC_ENABLED`. [V: config.py:232-281,473-478]
- **Skills/runaway/concurrencia**: `STACKY_SKILLS_ENABLED`/`_PROJECTS`, `STACKY_RUNAWAY_MAX_TURNS` (0), `STACKY_RUNAWAY_MAX_COST_USD` (0.0), `STACKY_MAX_CONCURRENT_RUNS` (0). [V: config.py:278-297]
- **Capa perceptible (Plan 23)**: `STACKY_ADO_RUN_FOOTER_ENABLED`, `STACKY_WEBHOOKS_V2_ENABLED`, `STACKY_DESKTOP_NOTIFY_ENABLED`, `STACKY_LIVE_TELEMETRY_ENABLED`, `STACKY_SELF_REVIEW_MODE` (off), `STACKY_ADO_FAILURE_COMMENT_ENABLED`, `STACKY_DIGEST_INTERVAL_HOURS` (0), `STACKY_PIPELINES_ENABLED`. [V: config.py:299-333]
- **Arnés/verificación (Plan 30-32)**: `STACKY_EXEC_VERIFICATION_*`, `STACKY_EXEC_REPAIR_*`, `STACKY_FAKE_GREEN_GUARD_*`, `STACKY_ACCEPTANCE_*`, `STACKY_RUN_PREFLIGHT_GATE_ENABLED`, `STACKY_VERIFY_TASK_BEFORE_CONSUMED_ENABLED`, `STACKY_OUTPUT_GROUNDING_*`, `STACKY_INTEGRITY_KPIS_ENABLED`. [V: config.py:339-672]
- **Calidad (Plan 29)**: `STACKY_ACCEPTANCE_CRITERIA_INJECTION_*`, `STACKY_ADAPTIVE_EFFORT_ENABLED`, `STACKY_EFFORT_FLOOR` (medium), `STACKY_CRITERIA_REPAIR_*`, `STACKY_CLI_FEWSHOT_*`, `STACKY_QUALITY_KPIS_ENABLED`. [V: config.py:601-641]
- **Motor invisible (Plan 27)**: `STACKY_COMPLEXITY_ESTIMATION_ENABLED`, `STACKY_RUN_REPAIR_ENABLED`, `STACKY_DIFFICULTY_ROUTING_ENABLED`, `STACKY_ADO_READ_CACHE_TTL_SEC` (0), `STACKY_RETRIEVAL_EXPANSION_ENABLED`, `STACKY_PARALLEL_INJECTORS_ENABLED`, `STACKY_ADO_PREWARM_ENABLED`, `STACKY_CAPS_ADVISOR_ENABLED`. [V: config.py:480-542]
- **Lifecycle/higiene (Plan 28)**: `STACKY_RUNNER_REAP_ON_CLOSE_ENABLED` (true), `STACKY_LOG_FLUSH_INCREMENTAL_ENABLED`, `STACKY_ORPHAN_REAPER_ENABLED` (true), `STACKY_ORPHAN_REAPER_INTERVAL_SEC` (0), `STACKY_STALL_WATCHDOG_SECONDS` (600), `STACKY_PENDING_TASK_STRICT_VALIDATION_ENABLED` (true), `STACKY_PUBLISH_IDEMPOTENT_GUARD_ENABLED`, `STACKY_RELIABILITY_KPIS_ENABLED`. [V: config.py:544-599]
- **Runtime selector (Plan 36)**: `STACKY_RUNTIME_STRICT` (true) — loguea cuando faltó el runtime y se aplicó el default; nunca lo cambia en silencio. [V: config.py:684-690]
- **Épica/brief (Plan 38-41)**: `STACKY_EPIC_FROM_BRIEF_ENABLED` (true), `STACKY_EPIC_AUTOPUBLISH_BACKEND` (true), `STACKY_EPIC_REPAIR_ENABLED` (true), `STACKY_EXECUTION_TRACE_ENABLED` (true), `STACKY_TRACE_PROMPT_TEXT_ENABLED` (false, privacidad). [V: config.py:692-722]
- **Plan 39**: `STACKY_DB_READONLY_DIRECTIVE_ENABLED` (false, nunca incluye password), `STACKY_EXECUTION_HISTORY_ENABLED` (false). [V: config.py:419-428]
- **Gateway de completion (SSD P1)**: `STACKY_COMPLETION_GATEWAY` (off/shadow/on, default off), `STACKY_AGENT_TOKEN` `<REDACTADO>`. [V: config.py:441-452]
- **Pre-run git (memoria colaborativa Fase C)**: `STACKY_PRE_RUN_GIT_PULL_*`, `STACKY_PRE_RUN_GIT_WORKSPACE_POLICY` (fetch_only_warn), timeouts. [V: config.py:454-467]
- **Perfil arnés**: `STACKY_HARNESS_PROFILE` ("", off/safe/full). [V: config.py:334-337]

## Secretos / integraciones (R5 — `<REDACTADO>`)
`ADO_ORG`, `ADO_PROJECT`, `ADO_PAT=<REDACTADO>`, `STACKY_AGENT_TOKEN=<REDACTADO>`. La directiva de DB read-only
nunca incluye el password. [V: config.py:435-437,452; config.py:419-424]

## Watchers (env directas leídas en app.py, no en Config)
`STACKY_OUTPUT_WATCHER_AUTO_CREATE_TASKS` (true), `STACKY_OUTPUT_WATCHER_ENABLED`/`_INTERVAL_SECONDS`,
`STACKY_MANIFEST_WATCHER_ENABLED`/`_INTERVAL_SECONDS`, `STACKY_REAPER_ENABLED`/`_INTERVAL_SECONDS`,
`STACKY_RECOVERY_ON_STARTUP`, `STACKY_EVALS_INTERVAL_HOURS`, `STACKY_DEMO_SEED_ENABLED`. [V: app.py:170-347]

## Paths (env directas — runtime_paths.py)
`STACKY_APP_ROOT`, `STACKY_DATA_DIR`, `STACKY_PROJECTS_DIR`, `STACKY_REPO_ROOT`, `STACKY_FRONTEND_DIST`,
`STACKY_HOME`, `STACKY_AGENTS_DIR`, `STACKY_RUNTIME_CONFIG`. [V: runtime_paths.py:37-211]
